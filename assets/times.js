// Render every [data-kickoff] (UTC ISO-8601) in the VIEWER's own locale + timezone,
// so the abbreviation shows as EDT / MDT / PDT / BST / ... for wherever they are.
// Server-rendered fallback text is the venue-local time (meaningful without JS).
(function () {
  function fmt(iso) {
    var d = new Date(iso);
    if (isNaN(d.getTime())) return null;
    return new Intl.DateTimeFormat(undefined, {
      weekday: "short", month: "short", day: "numeric",
      hour: "numeric", minute: "2-digit", timeZoneName: "short"
    }).format(d);
  }
  function apply() {
    var els = document.querySelectorAll("[data-kickoff]");
    for (var i = 0; i < els.length; i++) {
      var el = els[i];
      var local = fmt(el.getAttribute("data-kickoff"));
      if (!local) continue;
      var venueTime = el.getAttribute("data-venue-time");
      if (venueTime) el.setAttribute("title", "Venue local: " + venueTime);
      el.innerHTML = local + ' <span class="tznote">your time</span>';
      el.classList.add("is-local");
    }
  }
  if (document.readyState === "loading") {
    document.addEventListener("DOMContentLoaded", apply);
  } else {
    apply();
  }
})();
