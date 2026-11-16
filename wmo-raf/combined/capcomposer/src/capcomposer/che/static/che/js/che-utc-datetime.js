/* CHE Composer: UTC date/time enhancements, demonstration prototype.
 * Provides native browser calendar/time inputs; the Django datetime field
 * remains the canonical submitted field, with its name and id unchanged.
 * Never uses browser-local Date() conversions, which could shift UTC values.
 * If an existing datetime cannot be parsed safely, leave the original editor
 * visible instead of modifying its value.
 */
(function () {
  'use strict';
  function initialise(name) {
    var source = document.querySelector('input[name="' + name + '"]');
    if (!source || source.dataset.cheUtcEnhanced === 'true') return;
    if (source.type === 'hidden' || source.disabled) return;
    var current = (source.value || '').trim();
    // Django/Wagtail common ISO-like forms; accept seconds/microseconds/offset.
    var match = current.match(/^(\d{4}-\d{2}-\d{2})[ T](\d{2}):(\d{2})(?::\d{2}(?:\.\d+)?)?(?:Z|[+-]\d{2}:?\d{2})?$/);
    if (current && (!match || /[+-]\d{2}:?\d{2}$/.test(current))) {
      var hint = document.createElement('p');
      hint.className = 'che-utc-hint';
      hint.textContent = 'Use YYYY-MM-DD HH:MM:SS (24-hour UTC). The existing value was kept unchanged because its format needs review.';
      source.insertAdjacentElement('afterend', hint);
      return;
    }
    var nativeType = source.type === 'datetime-local' ? 'datetime-local' : 'text';
    var group = document.createElement('div');
    group.className = 'che-utc-editor';
    var dateLabel = document.createElement('label');
    dateLabel.textContent = 'Date (YYYY-MM-DD)';
    var date = document.createElement('input');
    date.type = 'date';
    date.className = 'che-utc-date';
    date.setAttribute('aria-label', name.replace('_', ' ') + ' date in UTC');
    date.value = match ? match[1] : '';
    var timeLabel = document.createElement('label');
    timeLabel.textContent = 'Time (HH:MM, UTC)';
    var time = document.createElement('input');
    time.type = 'time';
    time.step = 60;
    time.className = 'che-utc-time';
    time.setAttribute('aria-label', name.replace('_', ' ') + ' time in UTC');
    time.value = match ? match[2] + ':' + match[3] : '';
    dateLabel.appendChild(date);
    timeLabel.appendChild(time);
    var note = document.createElement('p');
    note.className = 'che-utc-hint';
    note.textContent = name === 'event_end'
      ? '24-hour UTC. Leave both fields blank while the event is ongoing.'
      : '24-hour UTC. Both date and time are required.';
    group.appendChild(dateLabel);
    group.appendChild(timeLabel);
    group.appendChild(note);
    source.insertAdjacentElement('beforebegin', group);
    source.dataset.cheUtcEnhanced = 'true';
    source.classList.add('che-utc-original');
    function sync() {
      // Avoid silently inventing a time (e.g. 00:00) on incomplete input.
      if (date.value && time.value) {
        source.value = nativeType === 'datetime-local'
          ? date.value + 'T' + time.value
          : date.value + ' ' + time.value + ':00';
      } else if (!date.value && !time.value) {
        source.value = '';
      } else {
        // Preserve the original source input visibly until valid or cleared.
        source.value = '';
      }
      source.dispatchEvent(new Event('input', {bubbles: true}));
      source.dispatchEvent(new Event('change', {bubbles: true}));
    }
    date.addEventListener('change', sync);
    time.addEventListener('change', sync);
    // Incomplete fields need visible validation; keep source accessible.
    var form = source.closest('form');
    if (form) {
      form.addEventListener('submit', function (event) {
        if ((date.value && !time.value) || (!date.value && time.value)) {
          event.preventDefault();
          note.textContent = 'Enter both the UTC date and time, or clear both fields.';
          if (!date.value) date.focus(); else time.focus();
        }
      });
    }
  }
  function initialiseAll() {
    initialise('event_start');
    initialise('event_end');
  }
  if (document.readyState === 'loading') document.addEventListener('DOMContentLoaded', initialiseAll);
  else initialiseAll();
})();
