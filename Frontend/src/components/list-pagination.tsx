"use client";

import { useEffect, useState } from "react";
import TablePagination from "@mui/material/TablePagination";

export function ListPagination({ count, page, pageSize, onPageChange, onPageSizeChange, disabled = false, label = "List pagination" }: {
  count: number; page: number; pageSize: number;
  onPageChange: (page: number) => void; onPageSizeChange: (size: number) => void;
  disabled?: boolean; label?: string;
}) {
  return <nav aria-label={label} className="border-t border-line bg-white">
    <TablePagination component="div" count={count} page={Math.min(page, Math.max(0, Math.ceil(count / pageSize) - 1))}
      rowsPerPage={pageSize} rowsPerPageOptions={[10, 25, 50]} showFirstButton showLastButton disabled={disabled}
      onPageChange={(_, next) => onPageChange(next)} onRowsPerPageChange={event => onPageSizeChange(Number(event.target.value))}
      sx={{ ".MuiTablePagination-toolbar": { flexWrap: "wrap", justifyContent: "flex-end", px: { xs: 1, sm: 2 } }, ".MuiTablePagination-spacer": { display: { xs: "none", sm: "block" } }, ".MuiTablePagination-selectLabel, .MuiTablePagination-displayedRows": { fontSize: 12 } }}/>
  </nav>;
}

/** Page an already-loaded list. Keys reset filters; refreshes retain the page. */
export function useListPagination<T>(items: T[], resetKey = "", label = "List pagination") {
  const [page, setPage] = useState(0);
  const [pageSize, setPageSize] = useState(10);
  const [previousKey, setPreviousKey] = useState(resetKey);
  const currentPage = previousKey === resetKey ? Math.min(page, Math.max(0, Math.ceil(items.length / pageSize) - 1)) : 0;
  useEffect(() => {
    if (previousKey !== resetKey) { setPreviousKey(resetKey); setPage(0); }
    else if (page !== currentPage) setPage(currentPage);
  }, [resetKey, previousKey, currentPage, page]);
  return {
    rows: items.slice(currentPage * pageSize, (currentPage + 1) * pageSize),
    reveal: (index: number) => setPage(Math.floor(Math.max(0, index) / pageSize)),
    controls: <ListPagination count={items.length} page={currentPage} pageSize={pageSize} label={label}
      onPageChange={setPage} onPageSizeChange={size => { setPageSize(size); setPage(0); }}/>,
  };
}
