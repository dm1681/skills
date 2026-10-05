// Example tracker extension: draws a `status` field (and optional `detail`)
// that a live state file sets on nodes. Copy and adapt; the library itself
// knows nothing about statuses.
window.diagramExtension = (() => {
  const STATUS = {
    pending: { mark: "", label: "Pending", definition: "Not started yet; drawn faded." },
    running: { mark: "…", label: "Running", definition: "In progress now; the shape pulses." },
    done:    { mark: "✓", label: "Done", definition: "Finished successfully." },
    failed:  { mark: "✕", label: "Failed", definition: "Stopped with an error." },
    skipped: { mark: "–", label: "Skipped", definition: "Will not run this time; dashed and faded." },
  };
  const known = (node) => STATUS[node.status];
  return {
    decorateNode(node, g, size, api) {
      if (!known(node)) return;
      g.dataset.status = node.status;
      const mark = STATUS[node.status].mark;
      if (!mark) return;
      g.append(api.sv("g", { class: "status-mark", transform: `translate(${size.w - 6},${size.h - 4})` },
        api.sv("circle", { r: 10 }), api.sv("text", { y: 4, "text-anchor": "middle" }, mark)));
    },
    nodeCard(node, place, api) {
      if (!known(node)) return null;
      const text = STATUS[node.status].label + (node.detail ? ` · ${node.detail}` : "");
      return [api.el("p", { class: "status-line", "data-status": node.status }, text)];
    },
    legend(view, api) {
      const used = Object.keys(STATUS).filter((s) => view.nodes.some((n) => n.status === s));
      if (!used.length) return [];
      return [api.el("h2", {}, "Status"), ...used.map((s) => api.el("div", {
        class: "legend-item", tabindex: 0,
        onpointerenter: () => api.lightUp(view.nodes.filter((n) => n.status === s).map((n) => n.id), () => false),
        onpointerleave: () => api.restoreFocus(),
      }, api.el("span", { class: "status-key", "data-status": s }, STATUS[s].mark || "·"),
         api.el("div", {}, api.el("span", { class: "legend-name" }, STATUS[s].label),
           api.el("span", { class: "legend-def" }, STATUS[s].definition))))];
    },
    searchText(node) { return [node.status, node.detail].filter(Boolean).join(" "); },
  };
})();
