"use strict";
/* Runs in <head> before first paint so the page never flashes the wrong theme.
   Saved choice wins; otherwise follow the operating system. */
(function () {
  var t = null;
  try { t = localStorage.getItem("theme"); } catch (e) { /* private mode */ }
  if (t !== "light" && t !== "dark") t = matchMedia("(prefers-color-scheme: dark)").matches ? "dark" : "light";
  document.documentElement.setAttribute("data-theme", t);
})();
