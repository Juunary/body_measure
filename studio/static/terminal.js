// The process panel: a terminal that renders polo-line's segment lines.
// A `frame` event replaces the previous frame line of the same station,
// which is what "\r\033[K" does on a real terminal.

export class Terminal {
  constructor(el) {
    this.el = el;
    this.frameEl = null;
    this.frameStation = null;
  }

  clear() {
    this.el.innerHTML = "";
    this.frameEl = null;
    this.frameStation = null;
  }

  _lineEl(segments, kind) {
    const div = document.createElement("div");
    div.className = "line" + (kind ? ` ${kind}` : "");
    for (const [text, styles] of segments) {
      if (!text) continue;
      const span = document.createElement("span");
      span.textContent = text;
      if (styles && styles.length) span.className = styles.map((s) => `t-${s}`).join(" ");
      div.appendChild(span);
    }
    if (!div.childNodes.length) div.appendChild(document.createTextNode(" "));
    return div;
  }

  line(segments, kind = "") {
    this.frameEl = null;
    this.el.appendChild(this._lineEl(segments, kind));
    this._scroll();
  }

  text(text, style = "grey", kind = "") {
    this.line([[text, style ? [style] : []]], kind);
  }

  frame(stationIndex, segments, final) {
    const fresh = this._lineEl(segments, "frame");
    if (this.frameEl && this.frameStation === stationIndex) {
      this.el.replaceChild(fresh, this.frameEl);
    } else {
      this.el.appendChild(fresh);
    }
    this.frameEl = final ? null : fresh;
    this.frameStation = stationIndex;
    this._scroll();
  }

  stage(name, status, detail, elapsed) {
    if (status !== "done") return;
    const tail = elapsed !== undefined ? `  ${elapsed.toFixed(1)} s` : "";
    this.line([["      ", []], ["✓ ", ["green"]], [name, ["green"]], [tail, ["grey"]]], "done");
  }

  _scroll() {
    this.el.scrollTop = this.el.scrollHeight;
  }
}
