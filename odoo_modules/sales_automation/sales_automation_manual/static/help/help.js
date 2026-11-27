/* 27 Nov 2026: the Help of Sales Automation, Store, Delivery and Insights.
   help.html?app=..        -> cards "User Manual" + "How It Works".
                              Neither card asks anything: each shows its 2 buttons right under the cards
                              (<App> Manual | Full Manual, or <App> steps | Full Flow steps);
                              only those buttons ask "Open here / new tab". One row open at a time.
   manual_pick.html?app=.. -> the same 2 buttons on their own page (kept for old links)
   manual.html?doc=..&app= -> the PDF, Back to help.html with the manual buttons open
   V goes on every link: browsers keep these pages 7 days, so bump it with changes. */
(function () {
  var V = '4';
  var BASE = '/sales_automation_manual/static/help/';
  var HOW = '/sales_automation_manual/static/src/help/';
  var APPS = {
    sa: { name: 'Sales Automation', icon: '💬', doc: 'sales_automation_manual.pdf', how: 'sa_how',
          line: 'Step by step with pictures: WhatsApp groups, enquiries, vendor prices and payment links. Press Play or watch the video.' },
    store: { name: 'Store', icon: '🏪', doc: 'store_manual.pdf', how: 'store_how',
             line: 'Step by step with pictures: the Shop Queue, enquiries that need you, orders, Quick and Express delivery. Press Play or watch the video.' },
    delivery: { name: 'Delivery', icon: '🛵', doc: 'delivery_manual.pdf', how: 'delivery_how',
                line: 'Step by step with pictures: shops, riders, sending orders out, the live map and delivery codes. Press Play or watch the video.' },
    insights: { name: 'Insights', icon: '📊', doc: 'insights_manual.pdf', how: 'insights_how',
                line: 'Step by step with pictures: customer and vendor ratings, rated rows, remarks and the conduct filter. Press Play or watch the video.' }
  };
  var FULL = 'full_manual.pdf';
  var DOCS = [FULL].concat(Object.keys(APPS).map(function (k) { return APPS[k].doc; }));

  var q = new URLSearchParams(location.search);
  var key = APPS[q.get('app')] ? q.get('app') : 'sa';
  var app = APPS[key];
  function page(name, extra) { return BASE + name + '?app=' + key + (extra || '') + '&v=' + V; }
  function esc(s) { return String(s).replace(/[&<>"]/g, function (c) { return { '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;' }[c]; }); }
  function card(href, tab, name, icon, title, line, cls) {
    return '<a class="pick' + (cls ? ' ' + cls : '') + '" href="' + esc(href) + '" data-tab="' + esc(tab) + '" data-name="' + esc(name) + '">' +
      '<span class="ic">' + icon + '</span><span class="t">' + esc(title) + '</span><span class="d">' + esc(line) + '</span></a>';
  }

  var mode = document.body.getAttribute('data-page');
  var root = document.getElementById('root');

  if (mode === 'help') {
    document.title = app.name + ' Help';
    // the 2 manual buttons: shown under the cards when User Manual is tapped (no question for the card)
    var manualRow =
      '<div class="row" id="row-manual" hidden><p class="sub">Which manual do you want to read?</p><div class="grid">' +
      card(page('manual.html', '&doc=' + app.doc), BASE + app.doc + '?v=' + V, app.name + ' Manual', app.icon, app.name + ' Manual',
           'Only the ' + app.name + ' screens, step by step.', 'small') +
      card(page('manual.html', '&doc=' + FULL), BASE + FULL + '?v=' + V, 'Full Manual', '📚', 'Full Manual',
           'Sales Automation, Store, Delivery and Insights in one book.', 'small') +
      '</div></div>';
    // the 2 How It Works buttons: this app's steps, or the Full Flow; Back returns here with this row open
    var backHow = encodeURIComponent(page('help.html', '&open=how'));
    var howRow =
      '<div class="row" id="row-how" hidden><p class="sub">Which steps do you want to follow?</p><div class="grid">' +
      card(HOW + app.how + '.html?back=' + backHow + '&v=' + V, HOW + app.how + '.html?v=' + V, app.name + ' steps', app.icon,
           app.name + ' steps', app.line, 'small') +
      card(HOW + 'full_flow.html?back=' + backHow + '&v=' + V, HOW + 'full_flow.html?v=' + V, 'Full Flow steps', '🔄', 'Full Flow steps',
           'From a new product with pictures to a delivered order and its stars: every step a new junior needs, with a video.', 'small') +
      '</div></div>';
    root.innerHTML =
      '<div class="wrap"><h1>' + esc(app.name) + ' Help</h1><p class="sub">Learn ' + esc(app.name) + ' your way</p><div class="grid">' +
      '<a class="pick toggle" href="#" data-row="row-manual" role="button" aria-expanded="false" aria-controls="row-manual">' +
        '<span class="ic">📖</span><span class="t">User Manual</span><span class="d">' +
        esc('The ' + app.name + ' manual, or the Full manual of all 4 apps. Read or print (PDF).') + '</span></a>' +
      '<a class="pick toggle" href="#" data-row="row-how" role="button" aria-expanded="false" aria-controls="row-how">' +
        '<span class="ic">🧭</span><span class="t">How It Works</span><span class="d">' +
        esc('Step by step with pictures and a video: the ' + app.name + ' steps, or the Full Flow from product to delivery.') + '</span></a>' +
      '</div>' + manualRow + howRow + '</div>';
  } else if (mode === 'pick') {
    document.title = 'User Manual - ' + app.name;
    root.innerHTML =
      '<div class="top"><a href="' + esc(page('help.html')) + '">&larr; Back</a><h1>User Manual</h1></div>' +
      '<div class="wrap under"><p class="sub">Which manual do you want to read?</p><div class="grid">' +
      card(page('manual.html', '&doc=' + app.doc), BASE + app.doc + '?v=' + V, app.name + ' Manual', app.icon, app.name + ' Manual',
           'Only the ' + app.name + ' screens, step by step.') +
      card(page('manual.html', '&doc=' + FULL), BASE + FULL + '?v=' + V, 'Full Manual', '📚', 'Full Manual',
           'Sales Automation, Store, Delivery and Insights in one book.') +
      '</div></div>';
  } else if (mode === 'doc') {
    var doc = DOCS.indexOf(q.get('doc')) >= 0 ? q.get('doc') : app.doc;
    var title = doc === FULL ? 'Full User Manual' : app.name + ' – User Manual';
    document.title = title;
    document.body.classList.add('doc');
    root.outerHTML =
      '<div class="top"><a href="' + esc(page('help.html', '&open=manual')) + '">&larr; Back</a><h1>' + esc(title) + '</h1>' +
      '<a class="s" href="' + esc(BASE + doc + '?v=' + V) + '" target="_blank" rel="noopener">Open in a new tab</a></div>' +
      '<div class="box"><iframe src="' + esc(BASE + doc + '?v=' + V) + '" title="' + esc(title) + '"></iframe></div>';
    return;
  }

  // the "where to open" question
  var ask = document.createElement('div');
  ask.className = 'ask'; ask.id = 'ask'; ask.setAttribute('role', 'dialog'); ask.setAttribute('aria-modal', 'true');
  ask.innerHTML = '<div class="qbox"><h2 id="askT">Open</h2><p>Where do you want to open it?</p>' +
    '<button class="here" id="here" type="button">Open here</button>' +
    '<button class="tab" id="tab" type="button">Open in a new tab</button>' +
    '<button class="no" id="no" type="button">Cancel</button></div>';
  document.body.appendChild(ask);
  var picked = null;
  // a toggle card shows/hides its row of buttons; it never asks
  function showRow(id, on) {
    document.querySelectorAll('a.toggle').forEach(function (b) {
      var mine = b.dataset.row === id && on;
      b.classList.toggle('sel', mine); b.setAttribute('aria-expanded', mine ? 'true' : 'false');
      document.getElementById(b.dataset.row).hidden = !mine;
    });
    if (on) { document.getElementById(id).scrollIntoView({ block: 'nearest' }); }
  }
  document.querySelectorAll('a.toggle').forEach(function (b) {
    b.addEventListener('click', function (ev) {
      ev.preventDefault();
      showRow(b.dataset.row, document.getElementById(b.dataset.row).hidden);
    });
  });
  if (q.get('open') && document.getElementById('row-' + q.get('open'))) { showRow('row-' + q.get('open'), true); }

  document.querySelectorAll('a.pick:not(.toggle)').forEach(function (a) {
    a.addEventListener('click', function (ev) {
      ev.preventDefault(); picked = a;
      document.getElementById('askT').textContent = 'Open ' + a.dataset.name;
      ask.classList.add('on'); document.getElementById('here').focus();
    });
  });
  function close() { ask.classList.remove('on'); if (picked) picked.focus(); }
  document.getElementById('here').onclick = function () { location.href = picked.getAttribute('href'); };
  document.getElementById('tab').onclick = function () { window.open(picked.dataset.tab, '_blank', 'noopener'); close(); };
  document.getElementById('no').onclick = close;
  ask.addEventListener('click', function (ev) { if (ev.target === ask) close(); });
  document.addEventListener('keydown', function (ev) { if (ev.key === 'Escape' && ask.classList.contains('on')) close(); });
})();
