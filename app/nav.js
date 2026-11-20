// One navigation bar for every page. To add or rename a page, change PAGES here.
(function () {
  const PAGES = [
    { href: "index.html", label: "Home" },
    { group: "Sports" },
    { href: "sports.html", label: "Strategy builder" },
    { href: "research.html", label: "Case studies" },
    { group: "Markets" },
    { href: "stocks.html", label: "Markets vs stocks" },
    { href: "strategies.html", label: "Strategies & hedging" },
    { group: "Results" },
    { href: "findings.html", label: "Strategy search" },
    { href: "zoo.html", label: "Strategy zoo" },
  ];
  const here = (location.pathname.split("/").pop() || "index.html").toLowerCase();
  const esc = (s) => String(s).replace(/[&<>"]/g, (c) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;" }[c]));
  const links = PAGES.map((p) => p.group ? `<span class="navgroup">${esc(p.group)}</span>`
    : `<a href="${p.href}"${p.href === here ? ' aria-current="page"' : ""}>${esc(p.label)}</a>`).join("");
  const bar = document.createElement("header");
  bar.className = "sitebar";
  bar.innerHTML = `<div class="sitebar-in"><a class="brand" href="index.html"><span class="brandmark" aria-hidden="true"></span>ArbLab</a>
    <nav class="sitenav" aria-label="Site">${links}</nav>
    <a class="gh" href="https://github.com/adiamlani130/KalshiArbitrageBettor" target="_blank" rel="noopener">GitHub ↗</a></div>`;
  document.body.prepend(bar);
  document.querySelectorAll("nav.pages").forEach((n) => n.remove());     // old per-page link rows
})();
