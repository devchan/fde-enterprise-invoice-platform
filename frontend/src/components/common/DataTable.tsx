import {
  flexRender,
  getCoreRowModel,
  getPaginationRowModel,
  getSortedRowModel,
  useReactTable,
  type ColumnDef,
  type RowSelectionState,
  type SortingState,
  type VisibilityState,
} from "@tanstack/react-table";
import {
  ArrowDown,
  ArrowUp,
  ChevronLeft,
  ChevronRight,
  ChevronsUpDown,
  Columns3,
  Download,
  type LucideIcon,
} from "lucide-react";
import { useState, type ReactNode } from "react";
import { Alert, AlertDescription } from "../ui/alert";
import { Button } from "../ui/button";
import { Checkbox } from "../ui/checkbox";
import { DropdownMenu, DropdownMenuCheckboxItem, DropdownMenuContent, DropdownMenuTrigger } from "../ui/dropdown-menu";
import { Table, TableBody, TableCell, TableHead, TableHeader, TableRow } from "../ui/table";
import { downloadCsv, toCsv } from "../../utils/csv";

export type BulkAction<TData> = {
  label: string;
  icon: LucideIcon;
  onClick: (rows: TData[]) => void;
  variant?: "default" | "outline" | "destructive";
};

// Generic client-side table shared by every list view (invoices, jobs, users, audit):
// sorting, pagination, column resizing always on; column visibility, CSV export, and
// row-selection/bulk-actions are opt-in per caller since not every table needs them.
export function DataTable<TData>({
  bulkActions,
  columns,
  data,
  emptyMessage,
  enableColumnVisibility,
  enableExport,
  enableRowSelection,
  error,
  getRowId,
  pageSize = 10,
}: {
  bulkActions?: Array<BulkAction<TData>>;
  columns: ColumnDef<TData>[];
  data: TData[];
  emptyMessage: string;
  enableColumnVisibility?: boolean;
  enableExport?: { filename: string };
  enableRowSelection?: boolean;
  error?: string;
  getRowId?: (row: TData) => string;
  pageSize?: number;
}) {
  const [sorting, setSorting] = useState<SortingState>([]);
  const [columnVisibility, setColumnVisibility] = useState<VisibilityState>({});
  const [rowSelection, setRowSelection] = useState<RowSelectionState>({});

  const selectionColumn: ColumnDef<TData> | null = enableRowSelection
    ? {
        id: "select",
        enableSorting: false,
        enableResizing: false,
        size: 40,
        header: ({ table }) => (
          <Checkbox
            aria-label="Select all rows"
            checked={table.getIsAllPageRowsSelected() || (table.getIsSomePageRowsSelected() && "indeterminate")}
            onCheckedChange={(value) => table.toggleAllPageRowsSelected(Boolean(value))}
          />
        ),
        cell: ({ row }) => (
          <Checkbox
            aria-label="Select row"
            checked={row.getIsSelected()}
            onCheckedChange={(value) => row.toggleSelected(Boolean(value))}
          />
        ),
      }
    : null;

  const table = useReactTable({
    columns: selectionColumn ? [selectionColumn, ...columns] : columns,
    data,
    columnResizeMode: "onChange",
    enableColumnResizing: true,
    enableRowSelection,
    getRowId,
    getCoreRowModel: getCoreRowModel(),
    getSortedRowModel: getSortedRowModel(),
    getPaginationRowModel: getPaginationRowModel(),
    onSortingChange: setSorting,
    onColumnVisibilityChange: setColumnVisibility,
    onRowSelectionChange: setRowSelection,
    initialState: { pagination: { pageSize } },
    state: { sorting, columnVisibility, rowSelection },
  });

  const rows = table.getRowModel().rows;
  const canPaginate = table.getPageCount() > 1;
  const selectedRows = table.getSelectedRowModel().rows.map((row) => row.original);

  function exportCsv() {
    if (!enableExport) return;
    // Every sorted row (not just the current page) — pagination is a display
    // concern only, exports should cover the full filtered/sorted dataset.
    const exportColumns = table.getVisibleLeafColumns().filter((column) => column.id !== "select" && column.accessorFn);
    const headers = exportColumns.map((column) => (typeof column.columnDef.header === "string" ? column.columnDef.header : column.id));
    const plainRows = table.getSortedRowModel().rows.map((row) =>
      Object.fromEntries(
        exportColumns.map((column) => [
          typeof column.columnDef.header === "string" ? column.columnDef.header : column.id,
          row.getValue(column.id),
        ]),
      ),
    );
    downloadCsv(enableExport.filename, toCsv(headers, plainRows));
  }

  return (
    <div className="space-y-3">
      {error ? (
        <Alert variant="destructive">
          <AlertDescription>{error}</AlertDescription>
        </Alert>
      ) : null}
      {enableColumnVisibility || enableExport || (bulkActions && selectedRows.length > 0) ? (
        <div className="flex flex-wrap items-center justify-between gap-2">
          <div className="flex flex-wrap gap-2">
            {bulkActions && selectedRows.length > 0
              ? bulkActions.map((action) => (
                  <Button
                    key={action.label}
                    onClick={() => action.onClick(selectedRows)}
                    size="sm"
                    type="button"
                    variant={action.variant ?? "outline"}
                  >
                    <action.icon className="h-4 w-4" />
                    {action.label} ({selectedRows.length})
                  </Button>
                ))
              : null}
          </div>
          <div className="flex gap-2">
            {enableColumnVisibility ? (
              <DropdownMenu>
                <DropdownMenuTrigger asChild>
                  <Button size="sm" type="button" variant="outline">
                    <Columns3 className="h-4 w-4" />
                    Columns
                  </Button>
                </DropdownMenuTrigger>
                <DropdownMenuContent align="end">
                  {table
                    .getAllLeafColumns()
                    .filter((column) => column.id !== "select" && column.getCanHide())
                    .map((column) => (
                      <DropdownMenuCheckboxItem
                        checked={column.getIsVisible()}
                        key={column.id}
                        onCheckedChange={(value) => column.toggleVisibility(Boolean(value))}
                        onSelect={(event) => event.preventDefault()}
                      >
                        {typeof column.columnDef.header === "string" ? column.columnDef.header : column.id}
                      </DropdownMenuCheckboxItem>
                    ))}
                </DropdownMenuContent>
              </DropdownMenu>
            ) : null}
            {enableExport ? (
              <Button onClick={exportCsv} size="sm" type="button" variant="outline">
                <Download className="h-4 w-4" />
                Export CSV
              </Button>
            ) : null}
          </div>
        </div>
      ) : null}
      <div className="rounded-md border">
        <Table style={{ width: table.getTotalSize() }}>
          <TableHeader>
            {table.getHeaderGroups().map((headerGroup) => (
              <TableRow key={headerGroup.id}>
                {headerGroup.headers.map((header) => {
                  const sorted = header.column.getIsSorted();
                  return (
                    <TableHead className="relative" key={header.id} style={{ width: header.getSize() }}>
                      {header.isPlaceholder ? null : header.column.id === "select" ? (
                        (flexRender(header.column.columnDef.header, header.getContext()) as ReactNode)
                      ) : (
                        <button
                          className="inline-flex items-center gap-1.5 disabled:cursor-default"
                          disabled={!header.column.getCanSort()}
                          onClick={header.column.getToggleSortingHandler()}
                          type="button"
                        >
                          {flexRender(header.column.columnDef.header, header.getContext())}
                          {sorted === "asc" ? (
                            <ArrowUp className="h-3.5 w-3.5" />
                          ) : sorted === "desc" ? (
                            <ArrowDown className="h-3.5 w-3.5" />
                          ) : header.column.getCanSort() ? (
                            <ChevronsUpDown className="h-3.5 w-3.5" />
                          ) : null}
                        </button>
                      )}
                      {header.column.getCanResize() ? (
                        <div
                          className="absolute right-0 top-0 h-full w-1 cursor-col-resize touch-none select-none hover:bg-primary/40"
                          onDoubleClick={() => header.column.resetSize()}
                          onMouseDown={header.getResizeHandler()}
                          onTouchStart={header.getResizeHandler()}
                        />
                      ) : null}
                    </TableHead>
                  );
                })}
              </TableRow>
            ))}
          </TableHeader>
          <TableBody>
            {rows.length === 0 ? (
              <TableRow>
                <TableCell className="text-center text-muted-foreground" colSpan={table.getAllLeafColumns().length}>
                  {emptyMessage}
                </TableCell>
              </TableRow>
            ) : (
              rows.map((row) => (
                <TableRow data-state={row.getIsSelected() ? "selected" : undefined} key={row.id}>
                  {row.getVisibleCells().map((cell) => (
                    <TableCell key={cell.id} style={{ width: cell.column.getSize() }}>
                      {flexRender(cell.column.columnDef.cell, cell.getContext())}
                    </TableCell>
                  ))}
                </TableRow>
              ))
            )}
          </TableBody>
        </Table>
      </div>
      {canPaginate ? (
        <div className="flex items-center justify-between text-sm text-muted-foreground">
          <span>
            Page {table.getState().pagination.pageIndex + 1} of {table.getPageCount()}
          </span>
          <div className="flex gap-2">
            <Button
              disabled={!table.getCanPreviousPage()}
              onClick={() => table.previousPage()}
              size="sm"
              type="button"
              variant="outline"
            >
              <ChevronLeft className="h-4 w-4" />
              Previous
            </Button>
            <Button disabled={!table.getCanNextPage()} onClick={() => table.nextPage()} size="sm" type="button" variant="outline">
              Next
              <ChevronRight className="h-4 w-4" />
            </Button>
          </div>
        </div>
      ) : null}
    </div>
  );
}
