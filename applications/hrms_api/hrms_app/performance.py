"""Performance orchestration over public native APIs; no core imports or SQL."""
from datetime import UTC, datetime
import hashlib

from pydantic import ValidationError

from .catalog import pack_by_type
from .custom_fields import check_custom, custom_keys
from .errors import AppError
from .performance_contracts import (ApproverChange, Assessment, Calibration, Comment, CycleInput,
                                    FeedbackInput, FeedbackReassignment, FeedbackRequest, GoalInput,
                                    Participants, Reassignment)
from .policy import capabilities, require
from .service import name

CYCLE = 'HRMS.PerformanceCycle'
REVIEW = 'HRMS.PerformanceReview'
GOAL = 'HRMS.PerformanceGoal'
FEEDBACK = 'HRMS.ProjectFeedback'
TYPES = (CYCLE, REVIEW, GOAL, FEEDBACK)
# Offered on open items for HR and managers to keep things moving; not anyone's next step.
TOOLS = frozenset({'reassign', 'withdraw', 'correct_rating', 'add_participants', 'change_approver', 'reassign_feedback', 'cancel_feedback'})


def today():
    return datetime.now(UTC).date().isoformat()


def check(condition, message, status=409):
    if not condition:
        raise AppError(status, message)


def parse(model, data):
    try:
        return model.model_validate(data).model_dump(mode='json')
    except ValidationError as exc:
        raise AppError(422, '; '.join(e['msg'] for e in exc.errors())) from exc


def plan_scope(plan, refs):
    """The existing records a plan changes, plus any it has created so far."""
    return {step['target'] for step in plan if step['op'] != 'create'} | set(refs.values())


class PerformanceService:
    def __init__(self, hrms):
        self.hrms, self.platform, self.journal = hrms, hrms.platform, hrms.journal

    def records(self, kind):
        pack = pack_by_type(kind)
        states = self.platform.states(pack.machine_name)
        return [{**r, 'kind': kind, 'state': states.get(r['entity_id'], 'not_enrolled')}
                for r in self.platform.records(kind, ['identifier', 'hrms_operation_key',
                                                      *[f['field'] for f in pack.fields], *custom_keys(self.platform, kind)])]

    def parse_with_custom(self, model, kind, data, current=None):
        """The screen's own fields through its contract; any others are fields added in Settings."""
        own = {k: v for k, v in data.items() if k in model.model_fields}
        return {**parse(model, own), **check_custom(self.platform, kind, {k: v for k, v in data.items() if k not in own}, current)}

    def snapshot(self):
        return {kind: self.records(kind) for kind in TYPES}

    def pending(self, actor):
        with self.journal.lock(actor.organization_id) as db:
            rows = db.execute("SELECT operation_key, progress FROM operations WHERE organization_id=%s AND actor_id=%s AND result IS NULL AND progress ? 'performance_request' ORDER BY updated_at",
                              (actor.organization_id, actor.user_id)).fetchall()
            return [dict(idempotency_key=key, **progress['performance_request']) for key, progress in rows]

    def user_options(self):
        users = []
        for user in self.platform.users():
            if user.get('status') != 'active' or user.get('email') == self.platform.email:
                continue
            caps = self.platform.user_capabilities(user['id'])
            users.append({'id': user['id'], 'name': user['full_name'], 'email': user['email'], 'capabilities': sorted(caps)})
        return users

    def options(self, actor):
        require(actor, 'performance:manage')
        users = self.user_options()
        active = {u['id'] for u in users}
        employees = self.hrms.employees()
        result = []
        for row in employees:
            d = row['data']
            if d.get('employment_status', '').lower() != 'active' or d.get('platform_user_id') not in active:
                continue
            managers = [m for m in employees if d.get('reports_to_employee_code')
                        and m['data'].get('employee_code') == d['reports_to_employee_code']]
            manager = managers[0] if len(managers) == 1 else None
            manager_id = manager['data'].get('platform_user_id') if manager else None
            if manager_id not in active or manager_id == d['platform_user_id']:
                manager, manager_id = None, None  # HR chooses who assesses them when the cycle is set up
            result.append(dict(id=row['entity_id'], name=name(row), employee_user_id=d['platform_user_id'],
                               manager_user_id=manager_id, manager_name=name(manager) if manager else None))
        return dict(employees=result, users=users,
                    approvers=[u for u in users if 'performance:approve_cycle' in u['capabilities'] and u['id'] != actor.user_id],
                    calibrators=[u for u in users if 'performance:manage' in u['capabilities']])

    @staticmethod
    def children(snap, kind, field, value):
        return [r for r in snap[kind] if r['data'].get(field) == value]

    def reviews_in(self, snap, cycle_id):
        """Reviews still taking part; withdrawn ones no longer hold the cycle up."""
        return [r for r in self.children(snap, REVIEW, 'cycle_id', cycle_id) if not r['data'].get('withdrawn_at')]

    def goals_of(self, snap, review_id):
        return [g for g in self.children(snap, GOAL, 'review_id', review_id) if not g['data'].get('removed_at')]

    def open_feedback(self, snap, review_id):
        return [f for f in self.children(snap, FEEDBACK, 'review_id', review_id) if not f['data'].get('cancelled_at')]

    @staticmethod
    def find(snap, entity_id):
        row = next((r for rows in snap.values() for r in rows if r['entity_id'] == entity_id), None)
        check(row is not None, 'Performance record was not found', 404)
        return row

    def allowed(self, actor, row, snap):
        d, state = row['data'], row['state']
        manage = 'performance:manage' in capabilities(actor)
        if row['kind'] == CYCLE:
            actions = []
            if manage and state == 'draft':
                actions += ['edit_cycle', 'submit']
            if (state == 'pending_approval' and actor.user_id == d['approver_id']
                    and actor.user_id not in {d['created_by'], d.get('submitted_by')}
                    and 'performance:approve_cycle' in capabilities(actor)):
                actions += ['approve', 'request_changes']
            if manage:
                actions += {'pending_approval': ['change_approver'], 'open': ['start_reviews', 'add_participants'],
                            'review': ['start_calibration', 'add_participants'], 'calibration': ['publish'],
                            'published': ['close']}.get(state, [])
            return actions
        if row['kind'] == FEEDBACK:
            if d.get('cancelled_at'):
                return []
            review = self.find(snap, d['review_id'])
            cycle = self.find(snap, review['data']['cycle_id'])
            if review['data'].get('withdrawn_at') or cycle['state'] == 'closed' or state != 'pending':
                return []
            actions = ['submit_feedback'] if (actor.user_id == d['reviewer_user_id'] and cycle['state'] in {'review', 'calibration'}
                                              and review['state'] == 'manager_review') else []
            if actor.user_id != review['data']['employee_user_id'] and (manage or actor.user_id == review['data']['manager_user_id']):
                actions += ['reassign_feedback', 'cancel_feedback']
            return actions
        if row['kind'] == GOAL:
            if d.get('removed_at'):
                return []
            review = self.find(snap, d['review_id'])
            if 'add_goal' not in self.allowed(actor, review, snap):
                return []
            return ['edit_goal'] + (['remove_goal'] if state in {'draft', 'changes_requested'} else [])
        if d.get('withdrawn_at'):
            return []
        cycle = self.find(snap, d['cycle_id'])
        if cycle['state'] in {'draft', 'pending_approval', 'closed'}:
            return []
        actions = []
        if manage and actor.user_id != d['employee_user_id']:
            if state not in {'published', 'acknowledged'}:
                actions += ['reassign', 'withdraw']
            elif cycle['state'] == 'published':
                actions += ['correct_rating']
        # Goals are set while the cycle is open; someone added later sets theirs during reviews.
        goal_setting = cycle['state'] in {'open', 'review'}
        if actor.user_id == d['employee_user_id']:
            if state == 'goals_draft' and goal_setting:
                actions += ['add_goal', 'submit_goals']
            if state == 'self_review' and cycle['state'] in {'review', 'calibration'}:
                actions += ['submit_self']
            if state == 'published' and cycle['state'] == 'published':
                actions += ['acknowledge']
            if state == 'acknowledged' and d.get('reacknowledge_required') and cycle['state'] == 'published':
                actions += ['acknowledge_correction']
        if actor.user_id == d['manager_user_id'] and actor.user_id != d['employee_user_id']:
            if state == 'goals_pending' and goal_setting:
                actions += ['approve_goals', 'return_goals']
            if state == 'manager_review' and cycle['state'] in {'review', 'calibration'}:
                actions += ['submit_manager', 'return_self', 'request_feedback']
        if (manage and actor.user_id == d['calibrator_user_id'] and actor.user_id != d['employee_user_id']
                and state == 'calibration' and cycle['state'] == 'calibration'):
            actions += ['calibrate', 'return_manager']
        return actions

    @staticmethod
    def due_date(kind, state, cycle):
        """The deadline the current step is working to, from the cycle's dates."""
        key = {CYCLE: {'open': 'goal_due_date', 'review': 'manager_review_due_date', 'calibration': 'end_date', 'published': 'end_date'},
               REVIEW: {'goals_draft': 'goal_due_date', 'goals_pending': 'goal_due_date', 'self_review': 'self_review_due_date',
                        'manager_review': 'manager_review_due_date', 'calibration': 'end_date', 'publish_ready': 'end_date',
                        'published': 'end_date'},
               FEEDBACK: {'pending': 'manager_review_due_date'}}.get(kind, {}).get(state)
        return str(cycle['data'].get(key))[:10] if key and cycle['data'].get(key) else None

    def dashboard(self, actor):
        snap = self.snapshot()
        manage = 'performance:manage' in capabilities(actor)
        reviews = []
        for row in snap[REVIEW]:
            d = row['data']
            own = d['employee_user_id'] == actor.user_id
            if not (manage or own or actor.user_id in (d['manager_user_id'], d['calibrator_user_id'])):
                continue
            cycle = self.find(snap, d['cycle_id'])
            if cycle['state'] in {'draft', 'pending_approval'}:
                continue
            data = {k: v for k, v in d.items() if k not in {'hrms_operation_key'}}
            # Own-review confidentiality takes precedence over any HR role held by the employee.
            if own and (row['state'] not in {'published', 'acknowledged'} or cycle['state'] not in {'published', 'closed'}):
                for field in ('manager_summary', 'manager_rating', 'calibrated_rating', 'final_rating', 'previous_final_rating'):
                    data.pop(field, None)
            if own:
                data.pop('calibration_comment', None)
            goals = [dict(id=g['entity_id'], state=g['state'], data={k: v for k, v in g['data'].items()
                       if k not in {'hrms_operation_key'}}, actions=self.allowed(actor, g, snap))
                     for g in self.goals_of(snap, row['entity_id'])]
            feedback = [] if own else [dict(id=f['entity_id'], kind=FEEDBACK, state='cancelled' if f['data'].get('cancelled_at') else f['state'],
                        data={k: v for k, v in f['data'].items() if k != 'hrms_operation_key'}, actions=self.allowed(actor, f, snap))
                        for f in self.children(snap, FEEDBACK, 'review_id', row['entity_id'])]
            withdrawn = bool(d.get('withdrawn_at'))
            reviews.append(dict(id=row['entity_id'], kind=REVIEW, state='withdrawn' if withdrawn else row['state'], data=data,
                                cycle_name=cycle['data']['name'], actions=self.allowed(actor, row, snap), goals=goals, feedback=feedback,
                                due_date=None if withdrawn or cycle['state'] == 'closed' else self.due_date(REVIEW, row['state'], cycle)))
        visible_cycles = {r['data']['cycle_id'] for r in reviews}
        cycles = []
        for row in snap[CYCLE]:
            d = row['data']
            if not (manage or d['approver_id'] == actor.user_id or row['entity_id'] in visible_cycles):
                continue
            data = {k: v for k, v in d.items() if k not in {'hrms_operation_key', 'participants'}}
            if manage or d['approver_id'] == actor.user_id:
                data['participants'] = d['participants']
            cycles.append(dict(id=row['entity_id'], kind=CYCLE, state=row['state'], data=data,
                               actions=self.allowed(actor, row, snap), due_date=self.due_date(CYCLE, row['state'], row)))
        assigned = []
        for row in snap[FEEDBACK]:
            if row['data']['reviewer_user_id'] == actor.user_id and not row['data'].get('cancelled_at'):
                review = self.find(snap, row['data']['review_id'])
                if review['data'].get('withdrawn_at'):
                    continue
                cycle = self.find(snap, review['data']['cycle_id'])
                assigned.append(dict(id=row['entity_id'], kind=FEEDBACK, state=row['state'],
                    data={k:v for k,v in row['data'].items() if k != 'hrms_operation_key'},
                    employee_name=review['data']['employee_name'], actions=self.allowed(actor, row, snap),
                    due_date=self.due_date(FEEDBACK, row['state'], cycle)))
        return dict(cycles=cycles, reviews=reviews, assigned_feedback=assigned, can_manage=manage)

    def workflows(self, actor):
        board = self.dashboard(actor)
        return [dict(entity_id=r['id'], entity_type=r['kind'],
                     title=r['data'].get('employee_name') or r['data'].get('name') or r.get('employee_name'),
                     identifier=r['data'].get('identifier', ''), current_state=r['state'],
                     workflow_label=pack_by_type(r['kind']).label,
                     owner_name=self.owner(r), next_action=', '.join(a.replace('_', ' ') for a in r['actions'] if a not in TOOLS) or
                         ('Withdrawn from the cycle' if r['state'] == 'withdrawn' else
                          'Complete' if r['state'] in {'closed', 'acknowledged', 'submitted'} else 'Waiting for assigned owner'),
                     progress=r.get('cycle_name', ''), due_date=r.get('due_date'), leave=None, leave_view=None)
                for r in [*board['cycles'], *board['reviews'], *board['assigned_feedback']]]

    @staticmethod
    def owner(row):
        d = row['data']
        if row['kind'] == REVIEW and row['state'] == 'publish_ready':
            return 'HR publication'
        key = {'goals_pending': 'manager_name', 'manager_review': 'manager_name',
               'calibration': 'calibrator_name', 'pending_approval': 'approver_name'}.get(row['state'], 'employee_name')
        return d.get(key) or d.get('reviewer_name') or 'HR'

    def participants(self, options, items):
        """Participants with the manager who assesses them: their reporting manager, or the one HR
        chose for someone without a reporting manager who has an active login."""
        users = {u['id']: u for u in options['users']}
        result = []
        for item in items:
            employee = next((e for e in options['employees'] if e['id'] == item['employee_id']), None)
            calibrator = next((u for u in options['calibrators'] if u['id'] == item['calibrator_user_id']), None)
            check(employee and calibrator, 'Every participant needs an active employee and an HR calibrator', 422)
            manager = users.get(item.get('manager_user_id') or employee['manager_user_id'] or '')
            check(manager is not None, f"Choose who assesses {employee['name']}: they have no reporting manager with an active login", 422)
            check(manager['id'] != employee['employee_user_id'], 'Employees cannot assess their own review', 422)
            check(calibrator['id'] != employee['employee_user_id'], 'Employees cannot calibrate their own review', 422)
            result.append(dict(employee_id=employee['id'], employee_name=employee['name'],
                employee_user_id=employee['employee_user_id'], manager_user_id=manager['id'],
                manager_name=manager['name'], calibrator_user_id=calibrator['id'], calibrator_name=calibrator['name']))
        check(len({p['employee_user_id'] for p in result}) == len(result), 'Duplicate employee login links need correction', 422)
        return result

    def cycle_data(self, actor, data, row=None):
        require(actor, 'performance:manage')
        parsed = self.parse_with_custom(CycleInput, CYCLE, data, row['data'] if row else None)
        check(parsed['end_date'] >= today(), 'The cycle end date has already passed', 422)
        options = self.options(actor)
        approver = next((u for u in options['approvers'] if u['id'] == parsed['approver_id']), None)
        created_by = row['data']['created_by'] if row else actor.user_id  # any HR can finish a colleague's draft
        check(approver is not None and approver['id'] != created_by, 'Select a different authorized cycle approver', 422)
        return {**parsed, 'participants': self.participants(options, parsed['participants']),
                'created_by': created_by, 'approver_name': approver['name']}

    def plan(self, actor, target, action, data, snap):
        ops = []
        def create(kind, values, owner, alias):
            ops.append(dict(op='create', kind=kind, data=values, owner=owner, target=alias))
        def patch(row, values):
            ops.append(dict(op='patch', target=row['entity_id'], data=values))
        def transition(row, trigger):
            ops.append(dict(op='transition', target=row['entity_id'], trigger=trigger))
        now = datetime.now(UTC).isoformat()
        if action == 'create_cycle':
            check(target == 'new', 'Use the cycle creation endpoint', 422)
            create(CYCLE, self.cycle_data(actor, data), actor.user_id, 'created')
            return ops
        row = self.find(snap, target)
        check(action in self.allowed(actor, row, snap), 'You cannot perform this action at the current stage', 403)
        d = row['data']
        if action == 'edit_cycle':
            patch(row, self.cycle_data(actor, data, row))
        elif row['kind'] == CYCLE:
            reviews = self.reviews_in(snap, target)
            if action == 'submit':
                check(d['approver_id'] != actor.user_id, 'You cannot approve a cycle you submit; choose another approver first', 422)
            elif action == 'approve':
                for index, participant in enumerate(d['participants']):
                    create(REVIEW, {**participant, 'cycle_id': target}, participant['employee_user_id'], f'review-{index}')
            elif action == 'request_changes':
                patch(row, {'decision_comment': parse(Comment, data)['comment']})
            elif action == 'change_approver':
                change = parse(ApproverChange, data)
                approver = next((u for u in self.options(actor)['approvers'] if u['id'] == change['approver_id']), None)
                check(approver is not None and approver['id'] not in {d['created_by'], d.get('submitted_by'), d['approver_id']},
                      'Choose an authorized approver who did not create or submit this cycle', 422)
                patch(row, {'approver_id': approver['id'], 'approver_name': approver['name'],
                            'decision_comment': f"Approver changed: {change['comment']}"})
                return ops
            elif action == 'add_participants':
                added = self.participants(self.options(actor), parse(Participants, data)['participants'])
                taking_part = {r['data']['employee_id'] for r in reviews}
                check(not any(p['employee_id'] in taking_part for p in added), 'Someone selected is already in this cycle', 409)
                for index, participant in enumerate(added):
                    create(REVIEW, {**participant, 'cycle_id': target}, participant['employee_user_id'], f'review-{index}')
                patch(row, {'participants': [*d['participants'], *added]})
                return ops
            elif action == 'start_reviews':
                check(today() >= str(d['start_date'])[:10], f"Reviews can start once the cycle begins on {str(d['start_date'])[:10]}", 409)
                check(reviews and all(r['state'] == 'self_review' for r in reviews), 'Every participant needs approved goals first')
            elif action == 'start_calibration':
                check(reviews and all(r['state'] == 'calibration' for r in reviews), 'All manager reviews must be submitted first')
            elif action == 'publish':
                check(reviews and all(r['state'] == 'publish_ready' for r in reviews), 'All reviews must be calibrated before publishing')
                for review in reviews:
                    patch(review, {'final_rating': review['data']['calibrated_rating'], 'published_at': now})
                    transition(review, 'publish')
            elif action == 'close':
                # Acknowledging confirms the employee has seen the outcome; it is not consent, so HR can
                # close without it. Unacknowledged reviews are counted on the cycle.
                check(reviews and all(r['state'] in {'published', 'acknowledged'} for r in reviews), 'Every review must be published first')
            transition(row, action)
            if action == 'submit':
                patch(row, {'submitted_by': actor.user_id})  # the submitter cannot also approve
            elif action == 'close':
                patch(row, {'unacknowledged_count': sum(r['state'] == 'published' for r in reviews)})
        elif row['kind'] == GOAL and action == 'remove_goal':
            patch(row, {'removed_at': now})
        elif action in {'add_goal', 'edit_goal'}:
            review = row if row['kind'] == REVIEW else self.find(snap, d['review_id'])
            cycle = self.find(snap, review['data']['cycle_id'])
            goal = self.parse_with_custom(GoalInput, GOAL, data, d if row['kind'] == GOAL else None)
            check(cycle['data']['start_date'] <= goal['target_date'] <= cycle['data']['end_date'], 'Goal target must be inside cycle dates', 422)
            if action == 'add_goal':
                create(GOAL, {**goal, 'review_id': target}, actor.user_id, 'created')
            else:
                patch(row, goal)
        elif row['kind'] == FEEDBACK:
            review = self.find(snap, d['review_id'])
            if action == 'cancel_feedback':
                patch(row, {'cancelled_at': now, 'cancelled_by': actor.user_id, 'cancel_reason': parse(Comment, data)['comment']})
            elif action == 'reassign_feedback':
                change = parse(FeedbackReassignment, data)
                reviewer = next((u for u in self.user_options() if u['id'] == change['reviewer_user_id']), None)
                check(reviewer and reviewer['id'] not in {review['data']['employee_user_id'], d['reviewer_user_id']},
                      'Select an active reviewer other than the employee and the current reviewer', 422)
                check(not any(f['data']['reviewer_user_id'] == reviewer['id'] and f['data']['project_reference'] == d['project_reference']
                              for f in self.open_feedback(snap, d['review_id'])), 'Feedback was already requested')
                patch(row, {'reviewer_user_id': reviewer['id'], 'reviewer_name': reviewer['name']})
            else:
                patch(row, self.parse_with_custom(FeedbackInput, FEEDBACK, data, d))
                transition(row, 'submit')
        else:
            goals = self.goals_of(snap, target)
            if action == 'reassign':
                assignment = parse(Reassignment, data)
                users = {u['id']: u for u in self.user_options()}
                manager = users.get(assignment['manager_user_id'])
                calibrator = users.get(assignment['calibrator_user_id'])
                check(manager and calibrator and 'performance:manage' in calibrator['capabilities'], 'Choose an active manager and HR calibrator', 422)
                check(d['employee_user_id'] not in {manager['id'], calibrator['id']}, 'Employees cannot assess or calibrate their own review', 422)
                patch(row, dict(manager_user_id=manager['id'], manager_name=manager['name'],
                                calibrator_user_id=calibrator['id'], calibrator_name=calibrator['name']))
                ops[-1]['previous_assignment'] = {key: d[key] for key in ('manager_user_id', 'manager_name', 'calibrator_user_id', 'calibrator_name')}
                return ops
            if action == 'withdraw':
                patch(row, {'withdrawn_at': now, 'withdrawn_by': actor.user_id, 'withdrawal_reason': parse(Comment, data)['comment']})
                return ops
            if action == 'correct_rating':
                value = parse(Calibration, data)
                check(value['rating'] != d.get('final_rating'), 'The corrected rating is the same as the published one', 422)
                patch(row, {'previous_final_rating': d.get('final_rating'), 'final_rating': value['rating'], 'calibrated_rating': value['rating'],
                            'rating_corrected_at': now, 'rating_corrected_by': actor.user_id, 'rating_correction_reason': value['comment'],
                            # An employee who already acknowledged sees the change and acknowledges again.
                            'reacknowledge_required': 'true' if row['state'] == 'acknowledged' else None})
                return ops
            if action == 'acknowledge_correction':
                patch(row, {**self.acknowledgement(data), 'reacknowledge_required': None})
                return ops
            if action in {'submit_goals', 'approve_goals'}:
                check(goals and sum(g['data']['weight'] for g in goals) == 100, 'Goal weights must total exactly 100%')
                expected = {'draft', 'changes_requested'} if action == 'submit_goals' else {'pending_approval'}
                check(all(g['state'] in expected for g in goals), 'Goals are not in the expected stage')
                for goal in goals:
                    transition(goal, 'submit' if action == 'submit_goals' else 'approve')
            elif action == 'return_goals':
                comment = parse(Comment, data)['comment']
                for goal in goals:
                    patch(goal, {'manager_comment': comment})
                    transition(goal, 'request_changes')
                patch(row, {'return_comment': comment})
            elif action in {'return_self', 'return_manager'}:
                field = 'calibration_comment' if action == 'return_manager' else 'return_comment'
                patch(row, {field: parse(Comment, data)['comment']})
            elif action in {'submit_self', 'submit_manager'}:
                assessment = parse(Assessment, data)
                if action == 'submit_self':
                    check(goals and all(g['state'] == 'approved' for g in goals), 'Approved goals are required')
                else:
                    check(all(f['state'] == 'submitted' for f in self.open_feedback(snap, target)),
                          'Requested project feedback is still pending; cancel or reassign it if the reviewer cannot respond')
                prefix = 'self' if action == 'submit_self' else 'manager'
                patch(row, {f'{prefix}_summary': assessment['summary'], f'{prefix}_rating': assessment['rating']})
            elif action == 'request_feedback':
                request = parse(FeedbackRequest, data)
                reviewer = next((u for u in self.user_options() if u['id'] == request['reviewer_user_id']), None)
                check(reviewer and reviewer['id'] != d['employee_user_id'], 'Select an active reviewer other than the employee', 422)
                check(not any(f['data']['reviewer_user_id'] == reviewer['id'] and f['data']['project_reference'] == request['project_reference']
                              for f in self.open_feedback(snap, target)), 'Feedback was already requested')
                create(FEEDBACK, {**request, 'review_id': target, 'reviewer_name': reviewer['name']}, reviewer['id'], 'created')
                return ops
            elif action == 'calibrate':
                value = parse(Calibration, data)
                patch(row, {'calibrated_rating': value['rating'], 'calibration_comment': value['comment']})
            elif action == 'acknowledge':
                patch(row, self.acknowledgement(data))
            transition(row, action)
        return ops

    @staticmethod
    def acknowledgement(data):
        check(set(data) <= {'comment'}, 'Only an acknowledgement comment is accepted', 422)
        comment = data.get('comment', '')
        check(isinstance(comment, str) and len(comment) <= 4000, 'Invalid comment', 422)
        return {'employee_comment': comment, 'acknowledged_at': datetime.now(UTC).isoformat()}

    def sync_employee(self, actor, employee_id):
        """Keep open reviews in step with the directory. A leaver's unpublished reviews are withdrawn
        and feedback asked of them is cancelled; a new reporting manager takes over manager steps
        not yet done. Best effort: the directory change has already been saved."""
        employee = next((r for r in self.hrms.employees() if r['entity_id'] == employee_id), None)
        if not employee:
            return
        d, now = employee['data'], datetime.now(UTC).isoformat()
        left = d.get('employment_status') == 'offboarded'
        users = {u['id']: u for u in self.user_options()}
        manager_row = next((m for m in self.hrms.employees() if d.get('reports_to_employee_code')
                            and m['data'].get('employee_code') == d['reports_to_employee_code']), None)
        manager = users.get(manager_row['data'].get('platform_user_id')) if manager_row else None
        with self.journal.lock(actor.organization_id) as db:
            snap = self.snapshot()
            changes = []
            for review in snap[REVIEW]:
                r = review['data']
                if r.get('employee_id') != employee_id or r.get('withdrawn_at') or self.find(snap, r['cycle_id'])['state'] == 'closed':
                    continue
                if left and review['state'] not in {'published', 'acknowledged'}:
                    changes.append((review, {'withdrawn_at': now, 'withdrawn_by': actor.user_id,
                                             'withdrawal_reason': 'Left the company'}, 'performance:withdraw'))
                elif (not left and manager and manager['id'] not in {r['manager_user_id'], r['employee_user_id']}
                        and review['state'] in {'goals_draft', 'goals_pending', 'self_review', 'manager_review'}):
                    changes.append((review, {'manager_user_id': manager['id'], 'manager_name': manager['name']}, 'performance:reassign'))
            if left and d.get('platform_user_id'):
                for feedback in snap[FEEDBACK]:
                    if (feedback['data'].get('reviewer_user_id') == d['platform_user_id'] and feedback['state'] == 'pending'
                            and not feedback['data'].get('cancelled_at')):
                        changes.append((feedback, {'cancelled_at': now, 'cancelled_by': actor.user_id,
                                                   'cancel_reason': 'Reviewer left the company'}, 'performance:cancel_feedback'))
            for row, values, event in changes:
                record = self.platform.record(row['entity_id'])
                self.platform.call('PUT', f"/entity-records/{row['entity_id']}", json={'data': {**record['data'], **values}})
                self.journal.audit(db, actor, event, row['entity_id'])

    def execute(self, actor, target, request):
        check(actor.organization_id == self.platform.org, 'Wrong organization', 403)
        if request.action in {'create_cycle', 'edit_cycle', 'submit', 'start_reviews', 'start_calibration', 'publish', 'close', 'calibrate',
                              'return_manager', 'reassign', 'withdraw', 'correct_rating', 'add_participants', 'change_approver'}:
            require(actor, 'performance:manage')
        if request.action in {'approve', 'request_changes'}:
            require(actor, 'performance:approve_cycle')
        payload = request.model_dump(mode='json')
        key = request.idempotency_key
        with self.journal.lock(actor.organization_id) as db:
            operation = self.journal.operation(db, actor, key, {'target': target, **payload})
            if operation.result is not None:
                return operation.result
            if 'performance_plan' not in operation.progress:
                self.check_not_interleaved(db, actor, key, {target})
                plan = self.plan(actor, target, request.action, request.data, self.snapshot())
                self.check_not_interleaved(db, actor, key, plan_scope(plan, {}))
                operation.checkpoint(performance_plan=plan, performance_request={'target': target, 'action': request.action, 'data': request.data}, step=0, refs={})
            plan = operation.progress['performance_plan']
            refs = operation.progress['refs']
            for index in range(operation.progress['step'], len(plan)):
                step = plan[index]
                try:
                    self.apply(actor, key, operation, plan, index, refs)
                except AppError as error:
                    if error.status < 500 and index == 0 and step['op'] != 'create':
                        # The platform refused the first change, so nothing was applied: leave no recovery behind.
                        for field in ('performance_plan', 'performance_request', 'step', 'refs', 'creating'):
                            operation.progress.pop(field, None)
                        operation.checkpoint()
                    raise
                operation.checkpoint(step=index + 1, refs=refs, creating=None)
            result = {'entity_id': refs.get('created', target), 'action': request.action}
            self.journal.audit(db, actor, f'performance:{request.action}', result['entity_id'], operation_key=key)
            operation.finish(result)
            return result

    def check_not_interleaved(self, db, actor, key, scope):
        """Never let an action touch records that an incompletely applied plan is still changing.
        Plans on other records (other employees' reviews, say) carry on."""
        rows = db.execute("SELECT actor_id, progress FROM operations WHERE organization_id=%s AND operation_key<>%s AND result IS NULL AND progress ? 'performance_plan'",
                          (actor.organization_id, key)).fetchall()
        for owner, progress in rows:
            if scope & plan_scope(progress['performance_plan'], progress.get('refs') or {}):
                action = progress.get('performance_request', {}).get('action', 'performance action')
                who = 'your' if owner == actor.user_id else next(
                    (f"{u['full_name']}'s" for u in self.platform.users() if u['id'] == owner), "another user's")
                raise AppError(409, f"This record needs recovery: {who} interrupted {action.replace('_', ' ')} must be resumed from Performance first.")

    def apply(self, actor, key, operation, plan, index, refs):
        step = plan[index]
        marker = hashlib.sha256(f'{actor.organization_id}:{key}:{index}'.encode()).hexdigest()
        if step['op'] == 'create':
            rows = self.platform.records(step['kind'], ['hrms_operation_key'])
            matches = [r for r in rows if r['data'].get('hrms_operation_key') == marker]
            check(len(matches) <= 1, 'Duplicate operation records need reconciliation')
            if matches:
                entity_id = matches[0]['entity_id']
            else:
                check(operation.progress.get('creating') != index, 'Creation result is uncertain; an administrator must reconcile before retrying')
                operation.checkpoint(creating=index)
                record = self.platform.create_record(step['kind'], {**step['data'], 'hrms_operation_key': marker}, step['owner'])
                entity_id = record['entity_id']
            self.platform.enroll(entity_id, pack_by_type(step['kind']).machine_name)
            refs[step['target']] = entity_id
        elif step['op'] == 'patch':
            record = self.platform.record(step['target'])
            self.platform.call('PUT', f"/entity-records/{step['target']}", json={'data': {**record['data'], **step['data']}})
        else:
            self.platform.call('POST', f"/entities/{step['target']}/transitions", json={
                'entity_id': step['target'], 'trigger': step['trigger'], 'idempotency_key': marker,
                'inputs': {'hrms_actor_id': actor.user_id, 'hrms_operation_key': key}})
