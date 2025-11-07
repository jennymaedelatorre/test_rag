// static/js/cilo_progress.js

document.addEventListener("DOMContentLoaded", () => {
  const ctx = document.getElementById("ciloProgressChart");

  if (ctx) {
    new Chart(ctx, {
      type: "bar",
      data: {
        labels: ["CILO 1", "CILO 2", "CILO 3"], // Example labels
        datasets: [
          {
            label: "Achievement (%)",
            data: [85, 70, 60, 90], // Example static values
            backgroundColor: [
              "#28a745",
              "#ffc107",
              "#da585aff"
            ],
            borderRadius: 8,
          },
        ],
      },
      options: {
        indexAxis: "y", // horizontal bars
        scales: {
          x: {
            beginAtZero: true,
            max: 100,
            title: {
              display: true,
              text: "Percentage (%)",
              font: { size: 14 }
            },
            grid: { display: false }
          },
          y: {
            ticks: { font: { size: 13 } },
            grid: { display: false }
          }
        },
        plugins: {
          legend: {
            display: false
          },
          title: {
            display: true,
            text: "CILO Attainment Progress",
            font: { size: 16, weight: "bold" }
          },
          tooltip: {
            callbacks: {
              label: (ctx) => `${ctx.parsed.x}% completed`
            }
          }
        }
      }
    });
  }
});
