(function() {
  var table = document.getElementById('emailTable');
  if (!table) return;
  var headers = table.querySelectorAll('.sortable');
  var currentCol = 0;
  var ascending = false;

  function sortTable(colIdx, type) {
    var tbody = table.querySelector('tbody');
    var rows = Array.from(tbody.querySelectorAll('tr'));

    rows.sort(function(a, b) {
      var aVal, bVal;
      if (type === 'date') {
        aVal = a.cells[colIdx].getAttribute('data-sort') || '';
        bVal = b.cells[colIdx].getAttribute('data-sort') || '';
      } else {
        aVal = (a.cells[colIdx].textContent || '').trim().toLowerCase();
        bVal = (b.cells[colIdx].textContent || '').trim().toLowerCase();
      }
      if (aVal < bVal) return ascending ? -1 : 1;
      if (aVal > bVal) return ascending ? 1 : -1;
      return 0;
    });

    rows.forEach(function(row) { tbody.appendChild(row); });
  }

  headers.forEach(function(th) {
    th.addEventListener('click', function() {
      var col = parseInt(th.dataset.col);
      var type = th.dataset.type;

      if (col === currentCol) {
        ascending = !ascending;
      } else {
        currentCol = col;
        ascending = true;
      }

      headers.forEach(function(h) {
        h.querySelector('.sort-arrow').textContent = '';
        h.querySelector('.sort-arrow').classList.remove('sort-arrow--active');
      });
      var arrow = th.querySelector('.sort-arrow');
      arrow.textContent = ascending ? '\u25B2' : '\u25BC';
      arrow.classList.add('sort-arrow--active');

      sortTable(col, type);
    });
  });
})();
