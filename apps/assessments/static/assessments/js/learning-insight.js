document.addEventListener("DOMContentLoaded", () => {
  const queue = document.querySelector(
    "[data-review-queue]"
  );

  if (!queue) return;

  const filters = Array.from(
    queue.querySelectorAll(
      "[data-review-filter]"
    )
  );

  const items = Array.from(
    queue.querySelectorAll(
      "[data-review-item]"
    )
  );

  const emptyState = queue.querySelector(
    "[data-review-empty]"
  );

  const matches = (
    item,
    filterName
  ) => {
    if (filterName === "all") {
      return true;
    }

    if (filterName === "wrong") {
      return (
        item.dataset.reviewStatus
        === "wrong"
      );
    }

    if (filterName === "unanswered") {
      return (
        item.dataset.reviewStatus
        === "unanswered"
      );
    }

    if (filterName === "slow") {
      return (
        item.dataset.reviewSlow
        === "1"
      );
    }

    return (
      item.dataset.reviewArea
      === filterName
    );
  };

  const applyFilter = (
    filterName
  ) => {
    let visibleCount = 0;

    filters.forEach((button) => {
      button.classList.toggle(
        "is-active",
        button.dataset.reviewFilter
          === filterName
      );
    });

    items.forEach((item) => {
      const visible = matches(
        item,
        filterName
      );

      item.classList.toggle(
        "is-hidden",
        !visible
      );

      if (visible) {
        visibleCount += 1;
      }
    });

    if (emptyState) {
      emptyState.classList.toggle(
        "is-hidden",
        visibleCount > 0
      );
    }
  };

  filters.forEach((button) => {
    button.addEventListener(
      "click",
      () => {
        applyFilter(
          button.dataset.reviewFilter
        );
      }
    );
  });
});
