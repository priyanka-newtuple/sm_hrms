/**
 * OrgSelector
 *
 * A dropdown component that allows super-admins to select which organization
 * they want to view/manage settings for.
 */

import { Building2, Check } from 'lucide-react';
import { useState, useRef, useEffect } from 'react';
import { useOrgSelector } from '../contexts/OrgSelectorContext';
import { Button } from '@/components/ui/button';
import DropdownTrigger from './DropdownTrigger';

export default function OrgSelector() {
  const { selectedOrgId, selectedOrg, availableOrgs, isSuperAdmin, isLoading, selectOrg } =
    useOrgSelector();
  const [isOpen, setIsOpen] = useState(false);
  const dropdownRef = useRef<HTMLDivElement>(null);

  // Close dropdown when clicking outside
  useEffect(() => {
    const handleClickOutside = (event: MouseEvent) => {
      if (dropdownRef.current && !dropdownRef.current.contains(event.target as Node)) {
        setIsOpen(false);
      }
    };

    document.addEventListener('mousedown', handleClickOutside);
    return () => document.removeEventListener('mousedown', handleClickOutside);
  }, []);

  // Don't render for non-super-admins
  if (!isSuperAdmin) {
    return null;
  }

  const displayName = selectedOrg ? selectedOrg.name : 'All Organizations';

  return (
    <div className="relative" ref={dropdownRef}>
      <DropdownTrigger
        onClick={() => setIsOpen(!isOpen)}
        disabled={isLoading}
        isOpen={isOpen}
        icon={<Building2 className="w-4 h-4 text-warning shrink-0" />}
        label={
          <span className="text-warning font-medium">
            {isLoading ? 'Loading...' : displayName}
          </span>
        }
        chevronClassName="text-warning"
        className="px-3 py-2 text-sm bg-warning-subtle border border-warning/30 rounded-lg hover:bg-warning-subtle transition-colors max-w-xs"
      />

      {isOpen && (
        <div className="absolute top-full left-0 mt-1 w-64 bg-popover text-popover-foreground rounded-lg shadow-lg border border-border z-50 max-h-80 overflow-y-auto">
          <div className="p-2">
            <div className="text-xs font-medium text-muted-foreground uppercase tracking-wide px-2 py-1">
              Select Organization
            </div>

            {/* Option to view own org (Platform) */}
            <Button
              variant="ghost"
              onClick={() => {
                selectOrg(undefined);
                setIsOpen(false);
              }}
              className={`w-full flex items-center gap-2 px-2 py-2 text-sm rounded-lg hover:bg-muted ${
                !selectedOrgId ? 'bg-cobalt/10 text-cobalt' : 'text-foreground'
              }`}
            >
              <Building2 className="w-4 h-4" />
              <span className="flex-1 text-left">My Organization (Platform)</span>
              {!selectedOrgId && <Check className="w-4 h-4" />}
            </Button>

            <div className="border-t border-border my-1" />

            {/* List of other organizations */}
            {availableOrgs
              .filter((org) => org.id !== '00000000-0000-0000-0000-000000000000') // Exclude Platform
              .map((org) => (
                <Button
                  key={org.id}
                  variant="ghost"
                  onClick={() => {
                    selectOrg(org.id);
                    setIsOpen(false);
                  }}
                  className={`w-full flex items-center gap-2 px-2 py-2 text-sm rounded-lg hover:bg-muted ${
                    selectedOrgId === org.id ? 'bg-cobalt/10 text-cobalt' : 'text-foreground'
                  }`}
                >
                  <Building2 className="w-4 h-4" />
                  <span className="flex-1 text-left truncate">{org.name}</span>
                  {selectedOrgId === org.id && <Check className="w-4 h-4" />}
                </Button>
              ))}

            {availableOrgs.filter((org) => org.id !== '00000000-0000-0000-0000-000000000000').length === 0 && (
              <div className="px-2 py-3 text-sm text-muted-foreground text-center">
                No other organizations found
              </div>
            )}
          </div>
        </div>
      )}
    </div>
  );
}
