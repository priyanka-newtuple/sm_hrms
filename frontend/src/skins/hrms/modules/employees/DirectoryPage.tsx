import { useQuery } from "@tanstack/react-query";
import { Plus } from "lucide-react";
import { useState } from "react";
import { Link } from "react-router-dom";

import { employeesApi } from "@/skins/hrms/api/employees";
import type { Employee } from "@/skins/hrms/api/types";
import { usePermission } from "@/skins/hrms/auth/usePermission";
import { Badge } from "@/skins/hrms/components/Badge";
import { Button } from "@/skins/hrms/components/Button";
import { Card, CardHeader, CardTitle } from "@/skins/hrms/components/Card";
import { Select, TextInput } from "@/skins/hrms/components/Form";
import { Table, type Column } from "@/skins/hrms/components/Table";
import { FEATURES } from "@/skins/hrms/lib/features";

import { EmployeeForm } from "./EmployeeForm";

export default function DirectoryPage() {
  const canCreate = usePermission(FEATURES.EMPLOYEE_DIRECTORY, "create");
  const [search, setSearch] = useState("");
  const [status, setStatus] = useState("");
  const [creating, setCreating] = useState(false);

  const { data, isLoading } = useQuery({
    queryKey: ["employees", search, status],
    queryFn: () =>
      employeesApi.list({ search: search || undefined, status: status || undefined }),
  });

  const columns: Column<Employee>[] = [
    {
      key: "name",
      header: "Name",
      render: (e) => (
        <Link to={`/employees/${e.id}`} className="font-medium text-gray-900 hover:text-cobalt">
          {e.full_name}
        </Link>
      ),
    },
    { key: "code", header: "Code", render: (e) => e.employee_code },
    { key: "dept", header: "Department", render: (e) => e.department },
    { key: "designation", header: "Designation", render: (e) => e.designation },
    { key: "manager", header: "Reports To", render: (e) => e.reports_to?.full_name ?? "—" },
    { key: "role", header: "Role", render: (e) => e.role.name },
    { key: "status", header: "Status", render: (e) => <Badge>{e.employment_status}</Badge> },
  ];

  return (
    <div>
      <div className="mb-6 flex items-center justify-between">
        <h1 className="text-2xl font-light tracking-tight text-gray-900">Employee Directory</h1>
        {canCreate && (
          <Button onClick={() => setCreating(true)}>
            <Plus size={16} /> Add Employee
          </Button>
        )}
      </div>

      <div className="mb-4 flex gap-3">
        <TextInput
          placeholder="Search by name, email or code…"
          value={search}
          onChange={(e) => setSearch(e.target.value)}
          className="max-w-xs"
        />
        <Select
          value={status}
          onChange={(e) => setStatus(e.target.value)}
          className="max-w-[12rem]"
        >
          <option value="">All statuses</option>
          <option value="active">Active</option>
          <option value="on_leave">On leave</option>
          <option value="offboarded">Offboarded</option>
        </Select>
      </div>

      <Card>
        <CardHeader>
          <CardTitle>{data?.total ?? 0} employees</CardTitle>
        </CardHeader>
        {isLoading ? (
          <p className="text-sm text-gray-600">Loading…</p>
        ) : (
          <Table columns={columns} rows={data?.items ?? []} />
        )}
      </Card>

      {creating && <EmployeeForm onClose={() => setCreating(false)} />}
    </div>
  );
}
