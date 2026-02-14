() => {
  /* ===== Shadow DOM helpers (Gradio) ===== */
  const appEl  = () => document.querySelector("gradio-app");
  const root   = () => (appEl() && appEl().shadowRoot) ? appEl().shadowRoot : document;
  const q      = (sel) => root().querySelector(sel);
  const qa     = (sel) => root().querySelectorAll(sel);

  /* Which left paragraph (pair) is focused + which left spans must stay bright */
  const current = {
    idx: null,
    keepIds: [],          // LEFT keep-bright span IDs
    dimLeftAll: false,    // remember “dim all left spans” across repaints
    anchorIds: [],        // LEFT anchors to re-bracket after repaint
    keepRightIds: [],     // RIGHT keep-bright span IDs
    anchorRightIds: [],   // RIGHT anchors to re-bracket after repaint
    selectedLeftId: null, // persist selection across repaint
    selectedRightId: null
  };

  /* ===== Visual helpers (hover + selection) ===== */
  const confBox = () => q('#conf_box');

  const hi = (id, col) => {
    const e = q('#' + CSS.escape(id));
    if (!e) return;
    if (e.classList.contains('selected')) return; // keep selection strong
    if (!('_bg' in e.dataset)) e.dataset._bg = e.style.backgroundColor || '';
    // Only apply color if provided; passing null keeps current background
    if (col != null) e.style.backgroundColor = col || e.style.backgroundColor;
    e.style.outline = '2px solid #000';
  };

  const bye = (id) => {
    const e = q('#' + CSS.escape(id));
    if (!e) return;
    if (e.classList.contains('selected')) return;
    const bg = ('_bg' in e.dataset) ? e.dataset._bg : '';
    e.style.backgroundColor = bg || '';
    e.style.outline = '';
  };

  const clearSelection = () => {
    qa('span.hl.selected, span.hl.dimmed, span.hl.anchor-hl').forEach(el => {
      el.classList.remove('selected','dimmed','anchor-hl');
      el.style.removeProperty('--anchor-color');
    });
    current.selectedLeftId = null;
    current.selectedRightId = null;
    qa('span.hl').forEach(el => {
      const bg = ('_bg' in el.dataset) ? el.dataset._bg : '';
      el.style.backgroundColor = bg || '';
      el.style.outline = '';
    });
    if (confBox()) confBox().textContent = 'Confidence: -';
  };

  /* Color + bracket an anchor with its own label color (or mate color) */
  function forceAnchor(el){
    if (!el) return;
    const col = el.dataset.selfcolor || el.dataset.hcolor || '#16a34a';
    el.style.setProperty('--anchor-color', col);
    el.classList.add('anchor-hl');
  }

  /* span dimming in LEFT pane */
  function dimLeftSpansExcept(keepIds = []) {
    const keep = new Set(keepIds);
    qa('#left_pane .hl').forEach(el => {
      if (keep.has(el.id)) {
        el.classList.remove('dimmed');
      } else {
        el.classList.add('dimmed');
      }
    });
  }
  function clearLeftSpanDimming(){
    qa('#left_pane .hl.dimmed').forEach(el => el.classList.remove('dimmed'));
  }

  /* span dimming in RIGHT pane */
  function dimRightSpansExcept(keepIds = []) {
    const keep = new Set(keepIds);
    qa('#right_pane .hl').forEach(el => {
      if (keep.has(el.id)) {
        el.classList.remove('dimmed');
      } else {
        el.classList.add('dimmed');
      }
    });
  }
  function clearRightSpanDimming(){
    qa('#right_pane .hl.dimmed').forEach(el => el.classList.remove('dimmed'));
  }

  /* ===== Paragraph dimming (left pane) ===== */
  function dimParagraphs(idx){
    if (idx == null) return;
    qa('#left_pane .para-box').forEach(pb => {
      const p = pb.getAttribute('data-idx');
      if (p === String(idx)) {
        pb.classList.add('para-focus');
        pb.classList.remove('para-dim');
      } else {
        pb.classList.remove('para-focus');
        pb.classList.add('para-dim');
      }
    });
  }
  function clearParagraphDimming(){
    qa('#left_pane .para-box').forEach(pb => pb.classList.remove('para-dim','para-focus'));
  }

  /* Reapply paragraph + span dimming after Gradio re-renders the left HTML */
  (function observeLeftRepaints(){
    const L = q('#left_pane');
    if (!L || !('MutationObserver' in window)) return;
    const obs = new MutationObserver(() => {
      setTimeout(() => {
        if (current.idx != null) dimParagraphs(current.idx);
        if (current.keepIds && current.keepIds.length){
          dimLeftSpansExcept(current.keepIds);
        } else if (current.dimLeftAll) {
          qa('#left_pane .hl').forEach(el => el.classList.add('dimmed'));
        }
        // Always re-apply brackets on known anchors after repaint
        (current.anchorIds || []).forEach(id => {
          const el = q('#' + CSS.escape(id));
          if (el) forceAnchor(el);
        });
        // Re-select the previously selected LEFT span if any
        if (current.selectedLeftId) {
          const el = q('#' + CSS.escape(current.selectedLeftId));
          if (el) {
            el.classList.add('selected');
            el.classList.remove('dimmed');
            el.style.outline = '2px solid #000';
          }
        }
      }, 0);
    });
    obs.observe(L, { childList: true, subtree: true, characterData: true });
  })();

  /* Reapply RIGHT dimming/anchors after right HTML repaints */
  (function observeRightRepaints(){
    const R = q('#right_pane');
    if (!R || !('MutationObserver' in window)) return;
    const obs = new MutationObserver(() => {
      setTimeout(() => {
        if (current.keepRightIds && current.keepRightIds.length){
          dimRightSpansExcept(current.keepRightIds);
        }
        (current.anchorRightIds || []).forEach(id => {
          const el = q('#' + CSS.escape(id));
          if (el) forceAnchor(el);
        });
        if (current.selectedRightId) {
          const el = q('#' + CSS.escape(current.selectedRightId));
          if (el) {
            el.classList.add('selected');
            el.classList.remove('dimmed');
            el.style.outline = '2px solid #000';
          }
        }
      }, 0);
    });
    obs.observe(R, { childList: true, subtree: true, characterData: true });
  })();

  /* ===== Bridge to Python (hidden textbox) ===== */
  function findBridgeBox(){
    return q('#bridge_click textarea, #bridge_click input');
  }
  function sendBridge(val){
    const box = findBridgeBox();
    if (!box) return false;
    box.value = val;
    box.dispatchEvent(new InputEvent('input', { bubbles: true, composed: true }));
    return true;
  }

  /* ===== Hover feedback (cross-highlight left/right) ===== */
  root().addEventListener('mouseover', ev => {
    const t = (ev.composedPath && ev.composedPath()[0]) || ev.target;
    const s = t && t.closest ? t.closest('span.hl') : null;
    if (s) {
      const tgt = s.dataset.target || '';
      if (s.dataset.kind === 'addition') {
        // New behavior: pair ONLY with another addition if present; never with anchors.
        const mateId = s.dataset.rmate || s.dataset.lmate || '';
        // Keep self as-is (no green/red wash), outline only:
        hi(s.id, null);
        // If there is an explicit addition mate, outline it too; otherwise do nothing cross-panel
        if (mateId) hi(mateId, null);
      } else {
        // Non-additions keep normal cross-highlight
        hi(s.id, s.dataset.hcolor || '');
        if (tgt) hi(tgt, s.dataset.hcolor || '');
      }
      const c = parseFloat(s.dataset.conf || '');
      if (confBox()) confBox().textContent = 'Confidence: ' + (isNaN(c) ? '-' : c.toFixed(3));
    }
  }, {capture:true});

  root().addEventListener('mouseout', ev => {
    const t = (ev.composedPath && ev.composedPath()[0]) || ev.target;
    const s = t && t.closest ? t.closest('span.hl') : null;
    if (s) {
      const tgt = s.dataset.target || '';
      bye(s.id);
      if (s.dataset.kind === 'addition') {
        const mateId = s.dataset.rmate || s.dataset.lmate || '';
        if (mateId) bye(mateId);
      } else {
        if (tgt) bye(tgt);
      }
    }
  }, {capture:true});

  /* ===== Click handling (no scrolling, no floating) ===== */
  root().addEventListener('click', function (e) {
    const path = e.composedPath ? e.composedPath() : [e.target];
    let target = null;
    for (const n of path) {
      if (n instanceof Element && n.matches && (n.matches('.hl') || n.matches('.para-box'))) {
        target = n; break;
      }
    }

    // A) Click on a highlighted LEFT span
    const span = target && target.matches('.hl') ? target : null;
    if (span && span.hasAttribute('data-pair') && span.hasAttribute('data-left')) {
      e.preventDefault();
      e.stopPropagation();

      // Toggle: if user clicks the same already-selected span → clear selection and state
      if (span.classList.contains('selected') &&
          ((span.hasAttribute('data-left')  && span.id === current.selectedLeftId) ||
          (span.hasAttribute('data-right') && span.id === current.selectedRightId))) {
        const pidx = parseInt(span.getAttribute('data-pair') || '0', 10);
        clearSelection();
        clearLeftSpanDimming();
        clearRightSpanDimming();
        current.keepIds = [];
        current.keepRightIds = [];
        current.anchorIds = [];
        current.anchorRightIds = [];
        current.dimLeftAll = false;
        // Re-render paragraph in neutral state
        sendBridge(`P:${pidx}`);
        e.stopImmediatePropagation();
        return;
      }

      clearSelection(); // only clear span selection; dimming handled below
      span.classList.add('selected');

      const mateId = span.dataset.target;
      // no fill on select — keep only the box
      span.style.outline = '2px solid #000';
      current.selectedLeftId = span.id;
      current.selectedRightId = mateId || null;
      if (mateId) {
        const mate = q('#' + CSS.escape(mateId));
        if (mate) {
          mate.classList.add('selected');
          mate.style.outline = '2px solid #000';
          mate.classList.remove('dimmed'); // ensure it is not dimmed on first paint
          // If LEFT click was on an "addition" span, force its mate (anchor) to green
          if (span.dataset.kind === 'addition') forceAnchor(mate);
        }
      }
      // RIGHT dimming: keep mate + right in-pane anchor if any
      const keepRight = [];
      if (mateId) keepRight.push(mateId); // the right *anchor* (target)
      if (span.dataset.kind === 'addition' && span.dataset.ranchor)
        keepRight.push(span.dataset.ranchor); // in-pane anchor (same as target in most cases)
      if (span.dataset.kind === 'addition' && span.dataset.rmate)
        keepRight.push(span.dataset.rmate);   // the right *addition mate* — keep it undimmed (blue)
      dimRightSpansExcept(keepRight);
      current.keepRightIds = keepRight.slice();
      current.anchorRightIds = [];
      if (span.dataset.kind === 'addition') {
        if (span.dataset.ranchor) current.anchorRightIds.push(span.dataset.ranchor);
      }
      // build "keep bright" set for left spans (clicked + its left-anchor if addition)
      const keep = [span.id];
      if (span.dataset.kind === 'addition' && span.dataset.lanchor) {
        keep.push(span.dataset.lanchor);
        // also green the left in-pane anchor itself
        const lEl = q('#' + CSS.escape(span.dataset.lanchor));
        if (lEl) lEl.classList.add('anchor-hl');
      }
      // Dim all other LEFT spans + remember this set for re-renders
      dimLeftSpansExcept(keep);
      current.keepIds = keep.slice();
      current.anchorIds = [];
      if (span.dataset.kind === 'addition') {
        if (span.dataset.lanchor) current.anchorIds.push(span.dataset.lanchor);
        if (span.dataset.selfanchor === '1') current.anchorIds.push(span.id);
      }

      // force-highlight the LEFT in-pane anchor when present
      if (span.dataset.kind === 'addition') {
        const la = span.dataset.lanchor;
        if (la) forceAnchor(q('#' + CSS.escape(la)));
        // And the RIGHT in-pane anchor when present (if we clicked a left span and it embeds right anchors too)
        const ra = span.dataset.ranchor;
        if (ra) forceAnchor(q('#' + CSS.escape(ra)));
        // Self-anchored: also bracket the clicked span itself to “green with brackets”
        if (span.dataset.selfanchor === '1') {
          forceAnchor(span);
        }
      }

      const pidx = parseInt(span.getAttribute('data-pair') || '0', 10);
      const lidx = span.getAttribute('data-left');
      // apply paragraph dimming immediately for snappy feel
      current.idx = pidx;
      dimParagraphs(current.idx);

      if (sendBridge(`S:${pidx}:${lidx}`)) {
        // no-op; already dimmed above
      }
      e.stopImmediatePropagation();
      return;
    }

    // C) Click on a highlighted RIGHT span
    if (span && span.hasAttribute('data-pair') && span.hasAttribute('data-right')) {
      e.preventDefault();
      e.stopPropagation();

      // Toggle: if user clicks the same already-selected span → clear selection and state
      if (span.classList.contains('selected') &&
          ((span.hasAttribute('data-left')  && span.id === current.selectedLeftId) ||
          (span.hasAttribute('data-right') && span.id === current.selectedRightId))) {
        const pidx = parseInt(span.getAttribute('data-pair') || '0', 10);
        clearSelection();
        clearLeftSpanDimming();
        clearRightSpanDimming();
        current.keepIds = [];
        current.keepRightIds = [];
        current.anchorIds = [];
        current.anchorRightIds = [];
        current.dimLeftAll = false;
        // Re-render paragraph in neutral state
        sendBridge(`P:${pidx}`);
        e.stopImmediatePropagation();
        return;
      }


      clearSelection();
      span.classList.add('selected');
      span.style.outline = '2px solid #000';
      current.selectedRightId = span.id;

      const mateId = span.dataset.target; // points to L-k-li
      // Fallback: for additions without data-target, try left anchor
      const laFallback = span.dataset.lanchor || '';
      current.selectedLeftId = mateId || null;
      if (mateId) {
        const mate = q('#' + CSS.escape(mateId));
        if (mate) {
          mate.classList.add('selected');
          mate.style.outline = '2px solid #000';
          mate.classList.remove('dimmed'); // guarantee not dimmed on first click
          // If RIGHT click was on an "addition" span, force its mate (anchor) to green
          if (span.dataset.kind === 'addition') forceAnchor(mate);
        }
      }

      // RIGHT dimming: keep selected right span + its right in-pane anchor (if any)
      const keepR = [span.id];
      if (span.dataset.kind === 'addition' && span.dataset.ranchor) keepR.push(span.dataset.ranchor);
      dimRightSpansExcept(keepR);
      current.keepRightIds = keepR.slice();
      // default: we are NOT in “dim all left” mode unless proven otherwise below
      current.dimLeftAll = false;
      current.anchorRightIds = [];
      if (span.dataset.kind === 'addition') {
        if (span.dataset.ranchor) current.anchorRightIds.push(span.dataset.ranchor);
        // Self-anchored: bracket the clicked span itself too
        if (span.dataset.selfanchor === '1') {
          forceAnchor(span);
          current.anchorRightIds.push(span.id);
        }
      }
      // dim all other LEFT spans, keep only the left anchor (and/or left mate) bright
      const keep = [];
      if (mateId) keep.push(mateId);
      // try anchor fallback for additions
      if (!mateId && laFallback) {
        keep.push(laFallback);
        current.selectedLeftId = laFallback;
      }
      if (span.dataset.kind === 'addition' && span.dataset.lanchor) {
        keep.push(span.dataset.lanchor);
      }
      if (keep.length) {
        dimLeftSpansExcept(keep);
        current.dimLeftAll = false;
      } else {
        // No known left mate yet → do NOT pre-dim; wait for Python to resolve a mate.
        clearLeftSpanDimming();
        current.dimLeftAll = false;
      }
      current.keepIds = keep.slice();     // always refresh keepIds
      // persist left anchor so we can re-apply brackets after re-render
      current.anchorIds = [];
      if (span.dataset.kind === 'addition') {
        const la = span.dataset.lanchor || mateId;
        if (la) {
          current.anchorIds = [la];
          const lEl = q('#' + CSS.escape(la));
          if (lEl) forceAnchor(lEl);
        }
      }

      // force-highlight the RIGHT in-pane anchor (anchor claim on the same B paragraph)
      if (span.dataset.kind === 'addition') {
        const ra = span.dataset.ranchor;
        if (ra) forceAnchor(q('#' + CSS.escape(ra)));
        // And the LEFT in-pane anchor (when addition is on the right)
        const la = span.dataset.lanchor;
        if (la) forceAnchor(q('#' + CSS.escape(la)));
      }

      const pidx = parseInt(span.getAttribute('data-pair') || '0', 10);
      const ridx = span.getAttribute('data-right');
      // apply paragraph dimming immediately; prevents “first click looks dimmed”
      current.idx = pidx;
      dimParagraphs(current.idx);

      if (sendBridge(`R:${pidx}:${ridx}`)) {
        // already set above
      }
      e.stopImmediatePropagation();
      return;
    }

    // B) Click on a LEFT paragraph card (anywhere on the card)
    const para = target && target.matches('.para-box') ? target : null;
    if (para && para.hasAttribute('data-idx')) {
      const idx = parseInt(para.getAttribute('data-idx') || '0', 10);

      clearSelection();  // ensure boxes/brackets from the last selection are removed immediately

      if (sendBridge(`P:${idx}`)) {
        current.idx = idx;
        dimParagraphs(current.idx);   // only dim, no scroll, no float
        // Clear span dimming if user clicks the card background
        clearLeftSpanDimming();
        clearRightSpanDimming();
        current.keepIds = [];
        current.keepRightIds = [];
        current.dimLeftAll = false;   // reset
        current.anchorIds = [];
        current.anchorRightIds = [];
        current.selectedLeftId = null;
        current.selectedRightId = null;
      }
    e.stopImmediatePropagation();
    return;
    }
  }, {capture:true});

  /* Clear dimming only when clicking outside BOTH panes (and not on a claim) */
  root().addEventListener('click', function (e) {
    const left  = q('#left_pane');
    const right = q('#right_pane');
    if (!left) return;

    const t = (e.composedPath && e.composedPath()[0]) || e.target;
    // If the click is inside either pane or on a claim span, don't clear.
    if ((left.contains(t) || (right && right.contains(t))) ||
        (t.closest && t.closest('span.hl'))) {
      return;
    }

    // Clicked outside the viewer → clear everything
    current.idx = null;
    clearParagraphDimming();
    clearLeftSpanDimming();
    clearRightSpanDimming();
    current.keepIds = [];
    current.keepRightIds = [];
    current.dimLeftAll = false;   // reset on outside click
    current.anchorIds = [];
    current.anchorRightIds = [];
  }, {capture:true});
}