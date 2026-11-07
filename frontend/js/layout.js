// Shared header + footer, injected into #site-header / #site-footer.
(function () {
  const path = location.pathname;
  const link = (href, label, active) =>
    `<a href="${href}" class="py-2 transition-colors whitespace-nowrap font-body-sm text-body-sm ${
      active ? "text-primary font-semibold border-b-2 border-primary" : "text-on-surface-variant hover:text-on-surface"
    }">${label}</a>`;

  document.getElementById("site-header").innerHTML = `
  <header class="fixed top-0 left-0 right-0 z-50 bg-surface-card/95 backdrop-blur-xl shadow-[0_1px_8px_rgba(0,0,0,0.04)]">
    <div class="max-w-[1360px] mx-auto px-gutter h-20 flex items-center justify-between gap-space-md">
      <a href="/" class="flex items-center gap-space-sm">
        <div class="w-9 h-9 rounded-xl bg-primary-container text-on-primary flex items-center justify-center font-bold">B</div>
        <div class="flex flex-col">
          <span class="font-headline-sm text-headline-sm leading-none font-bold text-on-surface">BXB</span>
          <span class="font-label-badge text-label-badge text-outline tracking-wider uppercase mt-0.5">Business Exchange Bureau</span>
        </div>
      </a>
      <nav class="hidden md:flex items-center gap-space-lg">
        ${link("/", "Marketplace", path === "/" || path.endsWith("index.html"))}
        ${link("/#sentiment", "Market Sentiment", false)}
        ${link("/#risk-report", "Legal Risk Reports", false)}
        ${link("/valuation.html", "AI Valuation", path.endsWith("valuation.html"))}
        ${link("/ai-lab.html", "AI Lab", path.endsWith("ai-lab.html"))}
      </nav>
      <div class="flex items-center gap-space-sm">
        <span class="hidden sm:inline-flex px-2.5 py-1 rounded bg-accent-gold-bg text-accent-gold font-label-badge text-label-badge uppercase font-bold">Demo · synthetic data</span>
      </div>
    </div>
  </header>`;

  document.getElementById("site-footer").innerHTML = `
  <footer class="w-full bg-surface-card mt-auto">
    <div class="max-w-[1360px] mx-auto px-gutter py-space-xl space-y-space-sm">
      <div class="bg-surface-container-low p-space-md rounded-xl">
        <p class="font-body-sm text-body-sm text-outline leading-relaxed">
          BXB Pulse is a development build. All listings, investors and enquiries shown here are synthetic and generated for
          demonstration. Asking prices are seller asks, not realised sale prices. Nothing here is investment, legal or tax advice.
        </p>
      </div>
      <span class="font-body-sm text-body-sm text-outline block">© 2026 BXB Pulse · AED-denominated</span>
    </div>
  </footer>`;
})();
