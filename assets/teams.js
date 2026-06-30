// Sort the team grid by country name (default) or FIFA rank, toggled by the
// .sort-toggle buttons. The grid is server-rendered in country-name order, so
// no-JS visitors already get the default sort; this only reorders in place on
// click — a pure progressive enhancement.
(function () {
  var grid = document.querySelector(".grid");
  var toggle = document.querySelector(".sort-toggle");
  if (!grid || !toggle) return;

  var cards = [];
  for (var i = 0; i < grid.children.length; i++) cards.push(grid.children[i]);

  function byName(a, b) {
    return a.getAttribute("data-name").localeCompare(b.getAttribute("data-name"));
  }
  function byRank(a, b) {
    return (
      parseInt(a.getAttribute("data-rank"), 10) - parseInt(b.getAttribute("data-rank"), 10)
    );
  }

  function apply(mode) {
    cards.sort(mode === "rank" ? byRank : byName);
    for (var i = 0; i < cards.length; i++) grid.appendChild(cards[i]);
    var btns = toggle.querySelectorAll("button");
    for (var j = 0; j < btns.length; j++) {
      var on = btns[j].getAttribute("data-sort") === mode;
      btns[j].classList.toggle("is-active", on);
      btns[j].setAttribute("aria-pressed", on ? "true" : "false");
    }
  }

  toggle.addEventListener("click", function (e) {
    var btn = e.target.closest("button[data-sort]");
    if (btn) apply(btn.getAttribute("data-sort"));
  });
})();
