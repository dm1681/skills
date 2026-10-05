/* semantic-pr-review's extension for the shared flow-diagram page.
   The page draws the visual language and knows nothing about pull requests;
   everything PR-specific lives here: the orientation block, build notices,
   change status, handoff cards, and markdown excerpts. The scaffold embeds
   the materialized PR model as MODEL.pr_model, and each hook looks its node
   or edge up there by id. Every node is built through the DOM, never
   innerHTML, so model text and excerpt text render as the literal text they
   are. */
window.diagramExtension = (() => {
  "use strict";

  // What the PR did, as a mark (never a hue: colour means kind on this page)
  // and as a sentence. A node may override the sentence with `change_note`.
  const CHANGE = {
    added: { mark: "+", label: "Added", sentence: "Added in this pull request." },
    modified: { mark: "~", label: "Modified", sentence: "Modified in this pull request." },
    removed: { mark: "−", label: "Removed", sentence: "Removed in this pull request." },
    context: { mark: "", label: "Context", sentence: "Unchanged context." },
  };
  const changeSentence = (status) => (CHANGE[status] || CHANGE.context).sentence;

  let index = null;
  function lookup(api) {
    if (!index) {
      const model = api.MODEL.pr_model;
      index = {
        model,
        nodes: new Map(model.nodes.map((n) => [n.id, n])),
        edges: new Map(model.edges.map((e) => [`${e.from}>${e.to}`, e])),
      };
    }
    return index;
  }

  // ---------- code-aware prose ----------
  // Long identifiers break only at CamelCase and snake_case boundaries.
  function appendSemanticCode(target, value) {
    const code = document.createElement("code");
    const text = String(value);
    for (let i = 0; i < text.length; i += 1) {
      const ch = text[i], prev = text[i - 1] || "", next = text[i + 1] || "";
      const camel = i > 0 && /[A-Z]/.test(ch) && (/[a-z0-9]/.test(prev) || (/[A-Z]/.test(prev) && /[a-z]/.test(next)));
      if (camel || prev === "_") code.append(document.createElement("wbr"));
      code.append(document.createTextNode(ch));
    }
    target.append(code);
  }
  function appendInlineCodeAware(target, value) {
    String(value || "").split(/(`[^`]+`)/g).filter(Boolean).forEach((part) => {
      if (part.startsWith("`") && part.endsWith("`")) appendSemanticCode(target, part.slice(1, -1));
      else target.append(document.createTextNode(part));
    });
  }
  const bulletMarker = /^[-*•]\s+/;
  // One line renders inline; several become block spans, a leading `- `
  // becoming a bullet whose wrapped text stays aligned. Spans rather than a
  // <ul>, so the result is valid inside a <p> or another <span>.
  function renderCodeAware(target, value) {
    const text = String(value || "");
    if (!text.includes("\n")) { appendInlineCodeAware(target, text); return target; }
    text.split("\n").forEach((raw) => {
      const line = raw.trim();
      if (!line) return;
      const bullet = bulletMarker.test(line);
      const row = document.createElement("span");
      row.className = bullet ? "prx-prose-bullet" : "prx-prose-line";
      appendInlineCodeAware(row, bullet ? line.replace(bulletMarker, "") : line);
      target.append(row);
    });
    return target;
  }
  const prose = (api, tag, cls, value) => renderCodeAware(api.el(tag, { class: cls }), value);

  // ---------- markdown excerpts ----------
  // A .md excerpt renders as the document it is. Only the drawing differs:
  // the excerpt bytes are untouched and verified against the blob.
  const mdInline =
    /(`[^`]+`|\*\*[^*]+\*\*|__[^_]+__|\*[^*\n]+\*|_[^_\n]+_|\[[^\]]+\]\((?:[^()\s]|\([^()\s]*\))+\))/g;
  const mdLink = /^\[([^\]]+)\]\(((?:[^()\s]|\([^()\s]*\))+)\)$/;
  // Only schemes that cannot execute script; a relative link has no base to
  // resolve against inside a card, so it stays plain text.
  const mdHref = (url) => (/^(?:https?:\/\/|mailto:)/i.test(url) ? url : "");

  function appendMarkdownInline(target, value) {
    String(value || "").split(mdInline).filter(Boolean).forEach((part) => {
      if (part.length > 1 && part.startsWith("`") && part.endsWith("`")) { appendSemanticCode(target, part.slice(1, -1)); return; }
      const strong = (part.startsWith("**") && part.endsWith("**")) || (part.startsWith("__") && part.endsWith("__"));
      if (strong && part.length > 4) { const n = document.createElement("strong"); appendMarkdownInline(n, part.slice(2, -2)); target.append(n); return; }
      const em = (part.startsWith("*") && part.endsWith("*")) || (part.startsWith("_") && part.endsWith("_"));
      if (em && part.length > 2) { const n = document.createElement("em"); appendMarkdownInline(n, part.slice(1, -1)); target.append(n); return; }
      const link = mdLink.exec(part);
      if (link) {
        const href = mdHref(link[2]);
        const n = document.createElement(href ? "a" : "span");
        if (href) { n.href = href; n.target = "_blank"; n.rel = "noopener"; n.className = "prx-md-link"; }
        appendMarkdownInline(n, link[1]);
        target.append(n);
        return;
      }
      target.append(document.createTextNode(part));
    });
  }

  function renderMarkdownExcerpt(target, source, api) {
    const lines = String(source).split("\n");
    let i = 0;
    const block = (cls, text, extra) => {
      const n = document.createElement("div");
      n.className = cls;
      Object.assign(n.dataset, extra || {});
      appendMarkdownInline(n, text);
      target.append(n);
    };
    while (i < lines.length) {
      const raw = lines[i], line = raw.trim();
      // An excerpt can open a fence it never closes; the rest is still code.
      const fence = /^(?:```|~~~)\s*([A-Za-z0-9_+-]*)\s*$/.exec(line);
      if (fence) {
        const body = [];
        i += 1;
        while (i < lines.length && !/^(?:```|~~~)\s*$/.test(lines[i].trim())) { body.push(lines[i]); i += 1; }
        i += 1;
        const pre = document.createElement("pre");
        pre.className = "prx-md-code";
        const code = document.createElement("code");
        api.highlight(code, body.join("\n"), fence[1].toLowerCase());
        pre.append(code);
        target.append(pre);
        continue;
      }
      i += 1;
      if (!line) continue;
      if (/^(?:-{3,}|\*{3,}|_{3,})$/.test(line)) { target.append(document.createElement("hr")); continue; }
      const heading = /^(#{1,6})\s+(.*)$/.exec(line);
      if (heading) { block("prx-md-heading", heading[2], { level: String(heading[1].length) }); continue; }
      const quote = /^>\s?(.*)$/.exec(line);
      if (quote) { block("prx-md-quote", quote[1]); continue; }
      const bullet = /^[-*+]\s+(.*)$/.exec(line), ordered = /^(\d+)[.)]\s+(.*)$/.exec(line);
      if (bullet || ordered) {
        const n = document.createElement("div");
        n.className = "prx-md-item";
        const indent = raw.length - raw.replace(/^\s+/, "").length;
        if (indent >= 2) n.dataset.indent = String(Math.min(3, Math.floor(indent / 2)));
        const marker = document.createElement("span");
        marker.className = "prx-md-marker";
        marker.textContent = ordered ? `${ordered[1]}.` : "•";
        const body = document.createElement("span");
        appendMarkdownInline(body, ordered ? ordered[2] : bullet[1]);
        n.append(marker, body);
        target.append(n);
        continue;
      }
      block("prx-md-line", line);
    }
  }

  // ---------- small parts ----------
  function changeLine(api, item) {
    const status = item.change_status;
    const line = prose(api, "div", "prx-change", String(item.change_note || "").trim() || changeSentence(status));
    line.dataset.changeStatus = status;
    return line;
  }
  function link(api, href, text) {
    return api.el("a", { class: "prx-source", href, target: "_blank", rel: "noopener" }, text, " ↗");
  }
  function field(api, label, value) {
    return api.el("div", { class: "prx-field" }, api.el("span", { class: "prx-field-name" }, label), prose(api, "span", "prx-field-value", value));
  }
  function codeList(api, items) {
    const span = api.el("span", { class: "prx-field-value" });
    items.forEach((item, i) => { if (i) span.append(", "); appendSemanticCode(span, item); });
    return span;
  }
  function markSvg(api, status) {
    const s = api.sv("svg", { viewBox: "0 0 46 26" });
    s.append(api.sv("rect", { x: 3, y: 4, width: 40, height: 18, rx: 5, class: "prx-legend-node" }));
    if (CHANGE[status]?.mark) {
      s.append(api.sv("path", { class: "prx-mark-bg", d: "M27,0 h19 v19 Z" }),
        api.sv("text", { class: "prx-mark-text", x: 40, y: 9, "text-anchor": "middle" }, CHANGE[status].mark));
    }
    return s;
  }
  function legendItem(api, svg, name, definition, onEnter) {
    return api.el("div", { class: "legend-item", tabindex: 0, onpointerenter: onEnter, onpointerleave: () => api.restoreFocus(),
      onfocus: onEnter, onblur: () => api.restoreFocus() },
      svg, api.el("div", {}, api.el("span", { class: "legend-name" }, name), api.el("span", { class: "legend-def" }, definition)));
  }

  // ---------- hooks ----------
  return {
    header(container, api) {
      const { model } = lookup(api);
      const pr = model.pr, s = model.summary;
      // The snapshot badge names the commit the excerpts came from; for a
      // deletion-only PR that is the pre-image, so both commits are shown.
      const snapshot = pr.evidence_sha
        ? `Analyzed snapshot · ${pr.evidence_sha.slice(0, 7)} (pre-image) · PR head ${pr.head_sha.slice(0, 7)}`
        : `Analyzed snapshot · ${pr.head_sha.slice(0, 7)}`;
      const orientation = api.el("section", { class: "prx-orientation", "data-pr-summary": true, "aria-label": "PR orientation" },
        api.el("div", { class: "prx-badges" },
          pr.url ? api.el("a", { class: "prx-badge", href: pr.url, target: "_blank", rel: "noopener" }, `PR ${pr.number} ↗`)
            : api.el("span", { class: "prx-badge" }, `PR ${pr.number}`),
          api.el("span", { class: "prx-badge", "data-role": "pr-snapshot" }, snapshot)),
        api.el("div", { class: "prx-orient-grid" },
          field(api, "Old → new", s.old_to_new),
          api.el("div", { class: "prx-field" }, api.el("span", { class: "prx-field-name" }, "Ownership"),
            api.el("span", { class: "prx-chain" }, ...s.ownership_chain.map((step) => api.el("span", { class: "prx-chain-step" }, step)))),
          field(api, "Payoff", s.payoff),
          field(api, "Residual debt", s.residual_debt)));
      container.append(orientation);

      // The reader never sees the operator's console, so a degraded build
      // explains itself here. An evidence anchor is a choice, not a fault.
      const notices = model.notices || [];
      const area = api.el("div", { class: "prx-notices", "data-role": "notices", role: "status" });
      if (notices.length) {
        const linkNotices = notices.filter((n) => n.startsWith("editor links omitted"));
        area.append(api.el("strong", {}, linkNotices.length ? "Some source links are unavailable in this build:" : "Build notes:"),
          ...notices.map((n) => api.el("span", {}, n)));
        if (linkNotices.length) area.append(api.el("span", {}, "Affected nodes fall back to their immutable GitHub links."));
      } else {
        area.hidden = true;
      }
      container.append(area);

      const rail = model.evidence_rail || [];
      if (rail.length) {
        container.append(api.el("section", { class: "prx-rail", "aria-label": "Cross-cutting evidence" },
          api.el("span", { class: "prx-badge" }, "Cross-cutting evidence · no runtime DTO"),
          ...rail.map((item) => api.el("div", { class: "prx-rail-item" }, api.el("strong", {}, item.label), " ", prose(api, "span", "", item.evidence)))));
      }
    },

    // A node card reads: summary (the page's own line), what the PR did, the
    // detail behind it, then what crosses the boundary.
    nodeCard(node, place, api) {
      const pn = lookup(api).nodes.get(node.id);
      if (!pn) return null;
      const detail = String(pn.purpose || "").trim().split("\n").slice(1).join("\n");
      const parts = [changeLine(api, pn)];
      if (detail) parts.push(prose(api, "div", "prx-detail", detail));
      if (place === "tip") {
        parts.push(prose(api, "p", "prx-handoff", `Receives: ${pn.receives}. Sends: ${pn.sends}.`));
        return parts;
      }
      parts.push(api.el("div", { class: "prx-fields" },
        field(api, "Receives", pn.receives), field(api, "Sends", pn.sends), field(api, "Role", pn.role),
        field(api, "Connection", pn.connection), field(api, "Tradeoff", pn.tradeoff)));
      parts.push(api.el("h2", {}, "Sources"), api.el("ul", { class: "prx-sources", "aria-label": "Relevant code" },
        ...pn.sources.map((src) => api.el("li", {},
          link(api, src.cursor_url || src.github_url, src.label),
          src.cursor_url ? link(api, src.github_url, "GitHub") : null))));
      return parts;
    },

    edgeCard(edge, api) {
      const pe = lookup(api).edges.get(`${edge.from}>${edge.to}`);
      if (!pe) return null;
      const parts = [changeLine(api, pe)];
      const fields = api.el("div", { class: "prx-fields" });
      if (edge.label !== pe.verb) fields.append(field(api, "Verb", pe.verb));
      fields.append(api.el("div", { class: "prx-field", "data-transfer": pe.transfer.join(", ") }, api.el("span", { class: "prx-field-name" }, "Transfers"),
        pe.transfer.length ? codeList(api, pe.transfer) : api.el("span", { class: "prx-field-value" }, "No runtime payload: control flow only.")));
      if (pe.optional?.length) fields.append(api.el("div", { class: "prx-field" }, api.el("span", { class: "prx-field-name" }, "Optional"), codeList(api, pe.optional)));
      if (pe.containers?.length) fields.append(api.el("div", { class: "prx-field" }, api.el("span", { class: "prx-field-name" }, "Containers"), codeList(api, pe.containers)));
      if (pe.transformation) fields.append(field(api, "Transformation", pe.transformation));
      if (pe.evidence) fields.append(field(api, "Evidence", pe.evidence));
      parts.push(fields);
      return parts;
    },

    sourceBlock(src, api) {
      if (src.lang !== "markdown") return null;
      const block = api.el("div", { class: "prx-markdown-preview" });
      renderMarkdownExcerpt(block, src.code, api);
      return block;
    },

    // The change mark is a corner delta carrying a symbol, so it never
    // depends on a second colour channel; a removed node is also dashed.
    decorateNode(node, g, size, api) {
      const pn = lookup(api).nodes.get(node.id);
      const status = pn ? pn.change_status : "context";
      g.dataset.changeStatus = status;
      if (status === "removed") g.classList.add("prx-removed");
      const mark = CHANGE[status]?.mark;
      if (!mark) return;
      g.append(api.sv("g", { class: "prx-mark", transform: `translate(${size.w - 22},-8)` },
        api.sv("path", { class: "prx-mark-bg", d: "M0,0 h26 v26 Z" }),
        api.sv("text", { class: "prx-mark-text", x: 18, y: 12, "text-anchor": "middle" }, mark),
        api.sv("title", {}, changeSentence(status))));
    },

    decorateEdge(edge, g, api) {
      const pe = lookup(api).edges.get(`${edge.from}>${edge.to}`);
      g.dataset.changeStatus = pe ? pe.change_status : "context";
    },

    legend(view, api) {
      const { model, nodes } = lookup(api);
      const shown = new Set(view.nodes.map((n) => n.id));
      const statuses = Object.keys(CHANGE).filter((s) => view.nodes.some((n) => nodes.get(n.id)?.change_status === s));
      const out = [api.el("h2", {}, "Change in this PR"), ...statuses.map((status) =>
        legendItem(api, markSvg(api, status), CHANGE[status].label,
          status === "context" ? "No mark: unchanged code shown for context." : `Corner ${CHANGE[status].mark}: ${changeSentence(status).toLowerCase()}`,
          () => api.lightUp(view.nodes.filter((n) => nodes.get(n.id)?.change_status === status).map((n) => n.id), () => false)))];
      // Every branch is visible at once; hovering one lights its whole run
      // from the shared trunk through convergence.
      if (model.branches.length > 1) {
        out.push(api.el("h2", {}, "Execution branches"));
        for (const branch of model.branches) {
          const path = [...model.shared_before, ...branch.path, model.convergence_node, ...model.shared_after].filter((id) => shown.has(id));
          const pairs = new Set(path.slice(1).map((id, i) => `${path[i]}>${id}`));
          const svg = api.sv("svg", { viewBox: "0 0 46 26" }, api.sv("path", { d: "M4,13 H42", class: "prx-branch-line" }));
          out.push(legendItem(api, svg, branch.label, `${branch.path.length} steps between dispatch and convergence.`,
            () => api.lightUp(path, (e) => pairs.has(`${e.from}>${e.to}`))));
        }
      }
      return out;
    },

    searchText(node, api) {
      const pn = lookup(api).nodes.get(node.id);
      return pn ? [pn.purpose, pn.receives, pn.sends, pn.role].join(" ") : "";
    },
  };
})();
