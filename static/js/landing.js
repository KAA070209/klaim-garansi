document.addEventListener("DOMContentLoaded", function () {
  // Menu mobile
  var header = document.getElementById("vsHeader");
  var burger = document.getElementById("vsBurger");
  var nav = document.getElementById("vsNav");

  if (header && burger && nav) {
    var setNav = function (open) {
      header.classList.toggle("is-nav-open", open);
      nav.classList.toggle("is-open", open);
      burger.setAttribute("aria-expanded", open ? "true" : "false");
      burger.setAttribute("aria-label", open ? "Tutup menu" : "Buka menu");
    };

    burger.addEventListener("click", function () {
      setNav(!nav.classList.contains("is-open"));
    });

    nav.querySelectorAll("a").forEach(function (link) {
      link.addEventListener("click", function () {
        setNav(false);
      });
    });

    window.addEventListener("resize", function () {
      if (window.innerWidth > 1023) {
        setNav(false);
      }
    });
  }

  // Ticker pengumuman
  var tickerItems = Array.prototype.slice.call(document.querySelectorAll(".vs-ticker-item"));
  var tickerPrev = document.getElementById("vsTickerPrev");
  var tickerNext = document.getElementById("vsTickerNext");
  var tickerIndex = 0;

  var showTicker = function (index) {
    if (!tickerItems.length) {
      return;
    }
    tickerIndex = (index + tickerItems.length) % tickerItems.length;
    tickerItems.forEach(function (item, i) {
      item.classList.toggle("is-active", i === tickerIndex);
    });
  };

  if (tickerItems.length > 1) {
    if (tickerPrev) {
      tickerPrev.addEventListener("click", function () {
        showTicker(tickerIndex - 1);
      });
    }
    if (tickerNext) {
      tickerNext.addEventListener("click", function () {
        showTicker(tickerIndex + 1);
      });
    }
    window.setInterval(function () {
      showTicker(tickerIndex + 1);
    }, 7000);
  }

  // Tab cek garansi
  var tabButtons = Array.prototype.slice.call(document.querySelectorAll("[data-vs-tab]"));
  var tabPanels = Array.prototype.slice.call(document.querySelectorAll("[data-vs-panel]"));

  tabButtons.forEach(function (button) {
    button.addEventListener("click", function () {
      var target = button.getAttribute("data-vs-tab");
      tabButtons.forEach(function (item) {
        var active = item === button;
        item.classList.toggle("is-active", active);
        item.setAttribute("aria-selected", active ? "true" : "false");
      });
      tabPanels.forEach(function (panel) {
        panel.classList.toggle("is-active", panel.getAttribute("data-vs-panel") === target);
      });
    });
  });

  // Tutup flash message
  document.querySelectorAll(".vs-flash-close").forEach(function (button) {
    button.addEventListener("click", function () {
      var alert = button.closest(".vs-flash-item");
      if (alert) {
        alert.remove();
      }
    });
  });

  // FAQ: satu item terbuka pada satu waktu
  var faqItems = Array.prototype.slice.call(document.querySelectorAll(".vs-faq-item"));
  faqItems.forEach(function (item) {
    item.addEventListener("toggle", function () {
      if (!item.open) {
        return;
      }
      faqItems.forEach(function (other) {
        if (other !== item) {
          other.open = false;
        }
      });
    });
  });
});
