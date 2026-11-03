/*
 * Progress chart (D-068, docs/ui-spec.md "L5 — Progress of an exercise"): for each
 * canvas[data-chart-src], fetches the chart JSON (same origin) and draws it with the vendored
 * Chart.js. Values, labels, tooltip titles, axis title, scale, tick step and tooltip text come
 * from the server, already in display units and in French; colours and fonts come from the CSS
 * tokens. Seconds on a duration axis are written m:ss / h:mm:ss (D-029, formatting only);
 * counts get whole ticks. On success the canvas gets data-chart-state="ready" and data-chart-ms
 * (time since navigation start); on failure the box is hidden again, the server-rendered
 * [data-chart-error] text is shown and the canvas gets data-chart-state="error". No user-facing
 * text, no business rule, no unit conversion here.
 */
(function () {
  "use strict";

  var SHAPES = ["circle", "rectRot", "rect", "triangle", "crossRot", "star"];
  var DARK = window.matchMedia ? window.matchMedia("(prefers-color-scheme: dark)") : null;

  function token(name) {
    return getComputedStyle(document.documentElement).getPropertyValue(name).trim();
  }

  function pad(number) {
    return (number < 10 ? "0" : "") + number;
  }

  // seconds -> "1:35", "1:02:05"; nothing below zero
  function clock(value) {
    var seconds = Math.round(value);
    if (seconds < 0) {
      return "";
    }
    var hours = Math.floor(seconds / 3600);
    var rest = seconds % 3600;
    var tail = pad(rest % 60);
    if (hours) {
      return hours + ":" + pad(Math.floor(rest / 60)) + ":" + tail;
    }
    return Math.floor(rest / 60) + ":" + tail;
  }

  function valueTicks(data) {
    if (data.scale === "duration") {
      return { stepSize: data.step || undefined, callback: clock };
    }
    return data.scale === "count" ? { precision: 0 } : {};
  }

  function fail(canvas) {
    var box = canvas.closest(".chart");
    var figure = canvas.closest("figure");
    var message = figure ? figure.querySelector("[data-chart-error]") : null;
    if (box) {
      box.hidden = true;
    }
    if (message) {
      message.hidden = false;
    }
    canvas.dataset.chartState = "error";
  }

  function datasets(series) {
    return series.map(function (item, index) {
      var points = item.kind === "points";
      return {
        label: item.label,
        data: item.values,
        pointStyle: SHAPES[index % SHAPES.length],
        pointRadius: points ? 5 : 4,
        pointHoverRadius: points ? 6 : 5,
        borderWidth: 2,
        showLine: !points,
        spanGaps: true,
        colourIndex: (index % SHAPES.length) + 1
      };
    });
  }

  function paint(chart) {
    var muted = token("--color-muted");
    var divider = token("--color-divider");
    chart.data.datasets.forEach(function (dataset) {
      var colour = token("--chart-" + dataset.colourIndex);
      dataset.borderColor = colour;
      dataset.backgroundColor = colour;
    });
    ["x", "y"].forEach(function (axis) {
      var scale = chart.options.scales[axis];
      scale.ticks.color = muted;
      scale.grid.color = divider;
      scale.border = { color: divider };
      scale.title.color = muted;
    });
    var tooltip = chart.options.plugins.tooltip;
    tooltip.backgroundColor = token("--color-surface");
    tooltip.titleColor = token("--color-text");
    tooltip.bodyColor = token("--color-text");
    tooltip.borderColor = token("--color-border");
  }

  function draw(canvas, data) {
    var box = canvas.closest(".chart");
    var style = getComputedStyle(box);
    Chart.defaults.font.family = style.fontFamily;
    Chart.defaults.font.size = parseFloat(style.fontSize);
    var chart = new Chart(canvas, {
      type: "line",
      data: { labels: data.labels, datasets: datasets(data.series) },
      options: {
        animation: false,
        responsive: true,
        maintainAspectRatio: false,
        locale: document.documentElement.lang || undefined,
        interaction: { mode: "index", intersect: false },
        plugins: {
          legend: { display: false },
          tooltip: {
            borderWidth: 1,
            usePointStyle: true,
            callbacks: {
              title: function (items) {
                return items.length && data.titles ? data.titles[items[0].dataIndex] : "";
              },
              label: function (context) {
                var value =
                  data.scale === "duration" ? clock(context.parsed.y) : context.formattedValue;
                return data.tooltip
                  .replace("{label}", context.dataset.label)
                  .replace("{value}", value);
              }
            }
          }
        },
        scales: {
          x: {
            ticks: { autoSkip: true, autoSkipPadding: 12, maxRotation: 0 },
            grid: {},
            title: { display: false }
          },
          y: { ticks: valueTicks(data), grid: {}, title: { display: true, text: data.axis } }
        }
      }
    });
    paint(chart);
    chart.update();
    if (DARK && DARK.addEventListener) {
      DARK.addEventListener("change", function () {
        paint(chart);
        chart.update();
      });
    }
  }

  function start(canvas) {
    var box = canvas.closest(".chart");
    if (box) {
      box.hidden = false;
    }
    if (typeof window.Chart === "undefined") {
      fail(canvas);
      return;
    }
    fetch(canvas.dataset.chartSrc, { headers: { Accept: "application/json" } })
      .then(function (response) {
        if (!response.ok) {
          throw new Error(String(response.status));
        }
        return response.json();
      })
      .then(function (data) {
        draw(canvas, data);
        canvas.dataset.chartState = "ready";
        canvas.dataset.chartMs = String(Math.round(performance.now()));
      })
      .catch(function () {
        fail(canvas);
      });
  }

  document.querySelectorAll("canvas[data-chart-src]").forEach(start);
})();
