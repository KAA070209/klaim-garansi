document.addEventListener("DOMContentLoaded", function () {
  // Tutup alert otomatis.
  document.querySelectorAll(".au-alert").forEach(function (alert) {
    var close = alert.querySelector(".au-alert-close");
    if (close) {
      close.addEventListener("click", function () {
        alert.remove();
      });
    }
    window.setTimeout(function () {
      if (document.body.contains(alert)) {
        alert.style.opacity = "0";
        alert.style.transition = "opacity 0.3s ease";
        window.setTimeout(function () {
          alert.remove();
        }, 320);
      }
    }, 6500);
  });

  // Tab portal: Pemilik Produk / Petugas Resmi.
  var portalTabs = Array.prototype.slice.call(document.querySelectorAll("[data-au-portal]"));
  var demoBoxes = Array.prototype.slice.call(document.querySelectorAll("[data-au-demo]"));
  portalTabs.forEach(function (tab) {
    tab.addEventListener("click", function () {
      var target = tab.getAttribute("data-au-portal");
      portalTabs.forEach(function (item) {
        var active = item === tab;
        item.classList.toggle("is-active", active);
        item.setAttribute("aria-selected", active ? "true" : "false");
      });
      demoBoxes.forEach(function (box) {
        box.classList.toggle("is-hidden", box.getAttribute("data-au-demo") !== target);
      });
    });
  });

  // Tab metode masuk: WhatsApp / SMS vs Email & Sandi.
  var methodTabs = Array.prototype.slice.call(document.querySelectorAll("[data-au-method]"));
  var methodPanels = Array.prototype.slice.call(document.querySelectorAll("[data-au-method-panel]"));
  methodTabs.forEach(function (tab) {
    tab.addEventListener("click", function () {
      var target = tab.getAttribute("data-au-method");
      methodTabs.forEach(function (item) {
        var active = item === tab;
        item.classList.toggle("is-active", active);
        item.setAttribute("aria-selected", active ? "true" : "false");
      });
      methodPanels.forEach(function (panel) {
        var match = panel.getAttribute("data-au-method-panel") === target;
        if (match) {
          panel.removeAttribute("hidden");
          panel.classList.add("is-active");
        } else {
          panel.setAttribute("hidden", "hidden");
          panel.classList.remove("is-active");
        }
      });
    });
  });

  // Tampilkan / sembunyikan formulir input nomor seri QR.
  var bypassToggle = document.getElementById("auBypassToggle");
  var bypassForm = document.getElementById("auBypassForm");
  if (bypassToggle && bypassForm) {
    bypassToggle.addEventListener("click", function () {
      var open = bypassForm.classList.toggle("is-hidden") === false;
      bypassToggle.setAttribute("aria-expanded", open ? "true" : "false");
      if (open) {
        var input = bypassForm.querySelector("input[name='token_qr']");
        if (input) {
          input.focus();
        }
      }
    });
  }

  // Tampilkan / sembunyikan kata sandi.
  document.querySelectorAll(".au-toggle-password").forEach(function (button) {
    button.addEventListener("click", function () {
      var field = button.closest(".au-input-icon");
      var input = field ? field.querySelector("input") : null;
      if (input) {
        input.type = input.type === "password" ? "text" : "password";
        input.focus();
      }
    });
  });
});
