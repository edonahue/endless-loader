document.addEventListener("DOMContentLoaded", () => {
  document.querySelectorAll("[data-knob-root]").forEach((root) => {
    const triggers = Array.from(root.querySelectorAll("[data-knob-trigger]"));
    const details = Array.from(document.querySelectorAll("[data-knob-detail]"));
    const defaultIndex = Number(root.getAttribute("data-default-knob") || 0);

    const activate = (index) => {
      triggers.forEach((trigger) => {
        trigger.classList.toggle(
          "is-active",
          Number(trigger.getAttribute("data-knob-trigger")) === index,
        );
      });
      details.forEach((detail) => {
        detail.classList.toggle(
          "is-active",
          Number(detail.getAttribute("data-knob-detail")) === index,
        );
      });
    };

    triggers.forEach((trigger) => {
      trigger.addEventListener("click", () => {
        activate(Number(trigger.getAttribute("data-knob-trigger")));
      });
    });

    activate(defaultIndex);
  });
});
