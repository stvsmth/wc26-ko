// Render every [data-kickoff] (UTC ISO-8601) in the VIEWER's own locale + timezone,
// so the abbreviation shows as EDT / MDT / PDT / BST / ... for wherever they are.
// Server-rendered fallback text is the venue-local time (meaningful without JS).
// Also upgrades [data-last-update] footers to the viewer's local timezone.
(function () {
  // Kickoffs lead with the weekday (which day of the tournament?); the footer
  // timestamp leads with the year instead. Same formatter, different field set.
  var KICKOFF_FMT = {
    weekday: "short", month: "short", day: "numeric",
    hour: "numeric", minute: "2-digit", timeZoneName: "short"
  };
  var UPDATE_FMT = {
    year: "numeric", month: "short", day: "numeric",
    hour: "numeric", minute: "2-digit", timeZoneName: "short"
  };
  function fmt(iso, opts) {
    var d = new Date(iso);
    if (isNaN(d.getTime())) return null;
    return new Intl.DateTimeFormat(undefined, opts).format(d);
  }
  function apply() {
    var els = document.querySelectorAll("[data-kickoff]");
    for (var i = 0; i < els.length; i++) {
      var el = els[i];
      var local = fmt(el.getAttribute("data-kickoff"), KICKOFF_FMT);
      if (!local) continue;
      var venueTime = el.getAttribute("data-venue-time");
      if (venueTime) el.setAttribute("title", "Venue local: " + venueTime);
      el.innerHTML = local;
      el.classList.add("is-local");
    }
    var updates = document.querySelectorAll("[data-last-update]");
    for (var j = 0; j < updates.length; j++) {
      var uel = updates[j];
      var uLocal = fmt(uel.getAttribute("data-last-update"), UPDATE_FMT);
      if (!uLocal) continue;
      uel.textContent = uLocal;
      uel.classList.add("is-local");
    }
  }
  if (document.readyState === "loading") {
    document.addEventListener("DOMContentLoaded", apply);
  } else {
    apply();
  }
})();
