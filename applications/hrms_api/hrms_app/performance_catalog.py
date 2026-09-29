"""HRMS-owned performance configuration installed through public platform APIs."""


def performance_packs(pack):
    def fields(strings=(), texts=(), integers=(), dates=(), jsons=()):
        return tuple({'field': name, 'type': kind} for kind, names in (
            ('string', strings), ('text', texts), ('integer', integers),
            ('date', dates), ('json', jsons)) for name in names)

    return (
        pack('HRMS.PerformanceCycle', 'Performance cycle', 'PFC', fields(
            strings=('name', 'created_by', 'approver_id', 'approver_name'),
            texts=('description', 'decision_comment'),
            dates=('start_date', 'end_date', 'goal_due_date', 'self_review_due_date', 'manager_review_due_date'),
            jsons=('participants',)), 'draft',
            ('draft', 'pending_approval', 'open', 'review', 'calibration', 'published', 'closed'),
            frozenset({'closed'}), (
                ('draft', 'submit', 'pending_approval'), ('pending_approval', 'approve', 'open'),
                ('pending_approval', 'request_changes', 'draft'), ('open', 'start_reviews', 'review'),
                ('review', 'start_calibration', 'calibration'), ('calibration', 'publish', 'published'),
                ('published', 'close', 'closed'))),
        pack('HRMS.PerformanceReview', 'Performance review', 'PFR', fields(
            strings=('cycle_id', 'employee_id', 'employee_user_id', 'employee_name', 'manager_user_id',
                     'manager_name', 'calibrator_user_id', 'calibrator_name', 'published_at', 'acknowledged_at'),
            texts=('self_summary', 'manager_summary', 'calibration_comment', 'employee_comment', 'return_comment'),
            integers=('self_rating', 'manager_rating', 'calibrated_rating', 'final_rating')),
            'goals_draft', ('goals_draft', 'goals_pending', 'self_review', 'manager_review',
                            'calibration', 'publish_ready', 'published', 'acknowledged'),
            frozenset({'acknowledged'}), (
                ('goals_draft', 'submit_goals', 'goals_pending'),
                ('goals_pending', 'approve_goals', 'self_review'),
                ('goals_pending', 'return_goals', 'goals_draft'),
                ('self_review', 'submit_self', 'manager_review'),
                ('manager_review', 'return_self', 'self_review'),
                ('manager_review', 'submit_manager', 'calibration'),
                ('calibration', 'return_manager', 'manager_review'),
                ('calibration', 'calibrate', 'publish_ready'),
                ('publish_ready', 'publish', 'published'),
                ('published', 'acknowledge', 'acknowledged'))),
        pack('HRMS.PerformanceGoal', 'Performance goal', 'PFG', fields(
            strings=('review_id', 'title', 'category'), texts=('description', 'measurement', 'evidence', 'manager_comment'),
            integers=('weight', 'progress'), dates=('target_date',)), 'draft',
            ('draft', 'pending_approval', 'approved', 'changes_requested'), frozenset({'approved'}), (
                ('draft', 'submit', 'pending_approval'), ('changes_requested', 'submit', 'pending_approval'),
                ('pending_approval', 'approve', 'approved'),
                ('pending_approval', 'request_changes', 'changes_requested'))),
        pack('HRMS.ProjectFeedback', 'Project feedback', 'PFF', fields(
            strings=('review_id', 'project_reference', 'reviewer_user_id', 'reviewer_name'),
            texts=('contribution', 'collaboration'), integers=('rating',)), 'pending',
            ('pending', 'submitted'), frozenset({'submitted'}), (('pending', 'submit', 'submitted'),)),
    )
