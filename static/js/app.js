function readJson(id) {
  const node = document.getElementById(id);
  if (!node) return null;
  return JSON.parse(node.textContent);
}

function drawCharts() {
  if (!window.echarts) return;
  const timelineNode = document.getElementById("timeline-chart");
  const timeline = readJson("timeline-data");
  if (timelineNode && timeline) {
    const chart = echarts.init(timelineNode);
    chart.setOption({
      tooltip: { trigger: "axis" },
      grid: { left: 40, right: 16, top: 24, bottom: 32 },
      xAxis: { type: "category", data: timeline.map((item) => item.date) },
      yAxis: { type: "value", min: 0, max: 100, name: "ИПА" },
      series: [{
        name: "ИПА",
        type: "line",
        connectNulls: false,
        data: timeline.map((item) => item.value),
        lineStyle: { color: "#1d4ed8", width: 2 },
        itemStyle: { color: "#1d4ed8" },
      }],
    });
  }
  const topicNode = document.getElementById("topic-chart");
  const topics = readJson("topic-data");
  if (topicNode && topics) {
    const chart = echarts.init(topicNode);
    chart.setOption({
      tooltip: { trigger: "item" },
      series: [{
        type: "pie",
        radius: ["42%", "70%"],
        data: topics.map((item) => ({ name: item.name, value: item.count })),
      }],
    });
  }
}

document.addEventListener("DOMContentLoaded", drawCharts);
document.body.addEventListener("htmx:afterSwap", drawCharts);
