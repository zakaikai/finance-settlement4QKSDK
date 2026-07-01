/** Factory functions for repeated AG Grid column definitions. */

const ROW_NO_STYLE = { color: 'var(--text-light)', backgroundColor: 'var(--palette-gray-50)', textAlign: 'center' }

export function rowNoCol(width = 50) {
  return { field: 'rowNo', headerName: '#', width, pinned: 'left',
    sortable: false, filter: false,
    valueFormatter: p => (p.node?.rowIndex ?? 0) + 1,
    cellStyle: ROW_NO_STYLE }
}

/** Percentage rate column: displays "12.50%", parses "12.5" → 0.125 */
export function rateCol(field, headerName, width = 110) {
  return { field, headerName, width, editable: true,
    valueFormatter: p => p.value != null ? (Number(p.value) * 100).toFixed(2) + '%' : '-',
    cellStyle: { textAlign: 'right' },
    valueParser: p => { const v = parseFloat(p.newValue); if (isNaN(v)) return 0; if (p.oldValue != null && Math.abs(v - p.oldValue) < 0.00001) return p.oldValue; return v / 100 } }
}

/** Date column with text editor (YYYY-MM-DD). */
export function dateCol(field, headerName, width = 120) {
  return { field, headerName, width, editable: true,
    cellEditor: 'agTextCellEditor',
    valueFormatter: p => p.value || '' }
}

/** Delete button column. */
export function deleteCol(onClick, width = 80) {
  return { headerName: '操作', width, editable: false, sortable: false, filter: false,
    cellRenderer: () => '<button class="btn-del-row" data-action="delete">删除</button>',
    onCellClicked: p => { if (p.event.target.dataset.action === 'delete') onClick(p) } }
}

/** Copy + delete button column. */
export function copyDeleteCol(onCopy, onDelete, width = 110) {
  return { headerName: '操作', width, editable: false, sortable: false, filter: false,
    cellRenderer: () => '<button class="btn-copy-row" data-action="copy">复制</button><button class="btn-del-row" data-action="delete">删除</button>',
    onCellClicked: p => {
      if (p.event.target.dataset.action === 'copy') onCopy(p)
      else if (p.event.target.dataset.action === 'delete') onDelete(p)
    } }
}
