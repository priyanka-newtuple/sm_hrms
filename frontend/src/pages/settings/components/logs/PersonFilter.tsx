import {
  Combobox,
  ComboboxContent,
  ComboboxEmpty,
  ComboboxInput,
  ComboboxItem,
  ComboboxList,
} from '@/components/ui/combobox';
import type { User } from '@/core/types';

type Props = {
  users: User[];
  value: string | null;
  onChange: (userId: string | null) => void;
  disabled?: boolean;
};

function userLabel(user: User): string {
  return user.full_name || user.email;
}

/** Search-by-name combobox over org users. Selects by id, never free text. */
export function PersonFilter({ users, value, onChange, disabled }: Props) {
  const selected = users.find((user) => user.id === value) ?? null;

  return (
    <Combobox
      value={selected}
      onValueChange={(user) => onChange((user as User | null)?.id ?? null)}
      items={users}
      itemToStringLabel={userLabel}
      itemToStringValue={(user: User) => user.id}
      disabled={disabled}
    >
      <ComboboxInput placeholder="Anyone" className="h-9 w-56" showClear />
      <ComboboxContent>
        <ComboboxEmpty>No people found.</ComboboxEmpty>
        <ComboboxList>
          {(user: User) => (
            <ComboboxItem key={user.id} value={user}>
              {userLabel(user)}
            </ComboboxItem>
          )}
        </ComboboxList>
      </ComboboxContent>
    </Combobox>
  );
}

export default PersonFilter;
