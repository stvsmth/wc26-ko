// Make every <table class="sortable"> sortable by clicking a column header.
// Headers opt in with [data-sort-type]: "num" (#, Age, Caps, Value), "pos"
// (GK/DF/MF/FW), or "text" (Player, Club). The server renders rows in squad
// (position) order; this only reorders in place on click, so it's a pure
// progressive enhancement — without JS the table still reads sensibly.
(function () {
  var POS_ORDER = { GK: 0, DF: 1, MF: 2, FW: 3 };

  // Sort value for one cell, given the column's declared type. Missing numeric
  // values (e.g. a "—" market value) return null so they always sink to the
  // bottom regardless of direction.
  function keyFor(cell, type) {
    if (type === "num") {
      var raw = cell.getAttribute("data-eur");
      if (raw === null) raw = cell.textContent;
      var n = parseFloat(raw);
      return isNaN(n) ? null : n;
    }
    if (type === "pos") {
      var span = cell.querySelector(".pos");
      var code = (span ? span.textContent : cell.textContent).trim();
      var o = POS_ORDER[code];
      return o === undefined ? null : o;
    }
    var explicit = cell.getAttribute("data-sort");
    return (explicit !== null ? explicit : cell.textContent).trim().toLowerCase();
  }

  function compare(a, b) {
    // nulls last, in either direction.
    if (a === null && b === null) return 0;
    if (a === null) return 1;
    if (b === null) return -1;
    if (a < b) return -1;
    if (a > b) return 1;
    return 0;
  }

  function sortBy(table, th, col, type) {
    var asc = th.getAttribute("aria-sort") !== "ascending";
    var tbody = table.tBodies[0];
    var rows = [];
    for (var i = 0; i < tbody.rows.length; i++) rows.push(tbody.rows[i]);

    rows.sort(function (r1, r2) {
      var c = compare(keyFor(r1.cells[col], type), keyFor(r2.cells[col], type));
      return asc ? c : -c;
    });

    for (var j = 0; j < rows.length; j++) tbody.appendChild(rows[j]);

    var heads = table.tHead.rows[0].cells;
    for (var k = 0; k < heads.length; k++) heads[k].removeAttribute("aria-sort");
    th.setAttribute("aria-sort", asc ? "ascending" : "descending");
  }

  function wire(table) {
    var heads = table.tHead ? table.tHead.rows[0].cells : [];
    for (var i = 0; i < heads.length; i++) {
      var th = heads[i];
      var type = th.getAttribute("data-sort-type");
      if (!type) continue;
      (function (th, col, type) {
        th.addEventListener("click", function () {
          sortBy(table, th, col, type);
        });
      })(th, i, type);
    }
  }

  function init() {
    var tables = document.querySelectorAll("table.sortable");
    for (var i = 0; i < tables.length; i++) wire(tables[i]);
  }

  if (document.readyState === "loading") {
    document.addEventListener("DOMContentLoaded", init);
  } else {
    init();
  }
})();
