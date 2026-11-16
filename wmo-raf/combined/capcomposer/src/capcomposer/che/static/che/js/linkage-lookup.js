/* CHE-only enhancement to the existing UUID input, without changing its value type.
   Does not execute on the CAP alert editor or other Wagtail admin pages. */
(() => {
  'use strict';
  function setup() {
    const uuidInput = document.getElementById('id_event_linkage');
    if (!uuidInput || uuidInput.dataset.cheLookupEnhanced) return;
    uuidInput.dataset.cheLookupEnhanced = 'true';

    const panel = document.createElement('div');
    panel.className = 'che-linkage-lookup';
    const heading = document.createElement('label');
    heading.htmlFor = 'che-linkage-search';
    heading.textContent = 'Find a higher-order event in this CHE catalogue';
    const search = document.createElement('input');
    search.id = 'che-linkage-search';
    search.type = 'search';
    search.autocomplete = 'off';
    search.placeholder = 'Search event type, hazard, institution, year or UUID';
    const note = document.createElement('p');
    note.textContent = 'Choose a record to fill the UUID field above. You can still enter an external CHE UUID directly.';
    note.className = 'che-linkage-note';
    const results = document.createElement('div');
    results.className = 'che-linkage-results';
    results.setAttribute('role', 'listbox');
    results.setAttribute('aria-label', 'Matching CHE events');
    const feedback = document.createElement('p');
    feedback.className = 'che-linkage-feedback';
    feedback.setAttribute('role', 'status');
    const clear = document.createElement('button');
    clear.type = 'button';
    clear.className = 'button button-small button-secondary';
    clear.textContent = 'Clear event linkage';
    clear.addEventListener('click', () => {
      uuidInput.value = '';
      uuidInput.dispatchEvent(new Event('change', {bubbles:true}));
      feedback.textContent = 'Event linkage cleared.';
    });
    panel.append(heading, search, note, results, feedback, clear);
    uuidInput.insertAdjacentElement('afterend', panel);
    let sequence = 0;
    let timer;
    let controller;
    function render(items) {
      results.replaceChildren();
      if (!items.length) { feedback.textContent = 'No matching local CHE events.'; return; }
      feedback.textContent = `${items.length} event(s) shown. Select one to fill the UUID above.`;
      for (const item of items) {
        const button = document.createElement('button');
        button.type = 'button';
        button.className = 'che-linkage-result';
        button.setAttribute('role', 'option');
        const title = document.createElement('strong');
        title.textContent = `${item.event_type} — ${item.hazard || '(unspecified hazard)'}`;
        const meta = document.createElement('small');
        meta.textContent = `${item.originator} · ${item.start} · ${item.status} · ${item.uuid}`;
        button.append(title, meta);
        button.addEventListener('click', () => {
          uuidInput.value = item.uuid;
          uuidInput.dispatchEvent(new Event('input', {bubbles:true}));
          uuidInput.dispatchEvent(new Event('change', {bubbles:true}));
          feedback.textContent = `Selected: ${item.event_type} — ${item.originator} (${item.uuid})`;
        });
        results.append(button);
      }
    }
    async function load() {
      const seq = ++sequence;
      if (controller) controller.abort();
      controller = new AbortController();
      feedback.textContent = 'Searching existing CHE records…';
      try {
        const url = new URL('/che/linkage-lookup/', window.location.origin);
        url.searchParams.set('q', search.value.trim());
        const response = await fetch(url, {credentials:'same-origin', signal:controller.signal});
        if (!response.ok) throw new Error(`HTTP ${response.status}`);
        const data = await response.json();
        if (seq === sequence) render(data.results || []);
      } catch (error) {
        if (error.name !== 'AbortError' && seq === sequence)
          feedback.textContent = `Event lookup unavailable: ${error.message}. You can still enter a UUID manually.`;
      }
    }
    search.addEventListener('input', () => {
      clearTimeout(timer);
      timer = setTimeout(load, 250);
    });
    load();
  }
  if (document.readyState === 'loading') document.addEventListener('DOMContentLoaded', setup);
  else setup();
})();
