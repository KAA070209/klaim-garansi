document.addEventListener("DOMContentLoaded", function () {
  // Menutup alert secara otomatis.
  document.querySelectorAll(".alert").forEach(function (alert) {
    var close = alert.querySelector(".close-alert");
    if (close) {
      close.addEventListener("click", function () {
        alert.remove();
      });
    }
    window.setTimeout(function () {
      if (document.body.contains(alert)) {
        alert.style.transition = "opacity 0.3s ease";
        alert.style.opacity = "0";
        window.setTimeout(function () {
          alert.remove();
        }, 320);
      }
    }, 6500);
  });

  // Konfirmasi untuk aksi berbahaya (tombol/link).
  document.querySelectorAll("[data-confirm]").forEach(function (element) {
    element.addEventListener("click", function (event) {
      if (!window.confirm(element.getAttribute("data-confirm"))) {
        event.preventDefault();
      }
    });
  });

  // Konfirmasi sebelum submit form yang memiliki data-confirm.
  document.querySelectorAll("form[data-confirm]").forEach(function (form) {
    form.addEventListener("submit", function (event) {
      if (!window.confirm(form.getAttribute("data-confirm"))) {
        event.preventDefault();
      }
    });
  });

  // Salin token / teks.
  document.querySelectorAll("[data-copy]").forEach(function (button) {
    button.addEventListener("click", function () {
      var text = button.getAttribute("data-copy") || "";
      var selesai = function () {
        var original = button.textContent;
        button.textContent = "Tersalin";
        window.setTimeout(function () {
          button.textContent = original;
        }, 1400);
      };
      if (navigator.clipboard && window.isSecureContext) {
        navigator.clipboard.writeText(text).then(selesai).catch(function () {});
      } else {
        var area = document.createElement("textarea");
        area.value = text;
        area.style.position = "fixed";
        area.style.opacity = "0";
        document.body.appendChild(area);
        area.select();
        try {
          document.execCommand("copy");
          selesai();
        } catch (error) {
          // Diabaikan.
        }
        document.body.removeChild(area);
      }
    });
  });

  // Tampilkan nama file yang dipilih.
  document.querySelectorAll("input[type='file'][data-file-label]").forEach(function (input) {
    var target = document.querySelector(input.getAttribute("data-file-label"));
    if (!target) {
      return;
    }
    input.addEventListener("change", function () {
      if (input.files && input.files.length) {
        target.textContent = input.files[0].name;
      } else {
        target.textContent = "";
      }
    });
  });

  // Alasan penolakan wajib diisi saat status ditolak.
  var statusSelect = document.querySelector("[data-status-select]");
  var reasonWrap = document.querySelector("[data-reason-wrap]");
  var reasonInput = document.querySelector("[data-reason-input]");
  if (statusSelect && reasonWrap && reasonInput) {
    var aturAlasan = function () {
      var perlu = statusSelect.value === "ditolak";
      reasonWrap.style.display = perlu ? "" : "none";
      reasonInput.required = perlu;
    };
    statusSelect.addEventListener("change", aturAlasan);
    aturAlasan();
  }

  // Tombol cetak.
  document.querySelectorAll("[data-print]").forEach(function (button) {
    button.addEventListener("click", function () {
      window.print();
    });
  });
});
