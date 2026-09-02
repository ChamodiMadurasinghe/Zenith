const major = Number.parseInt(process.versions.node.split('.')[0], 10);
if (major > 22) {
  console.error(
    `[bridge] Node ${process.version} is not supported by whatsapp-web.js (use Node 18–22).\n` +
      '[bridge] Install Node 20 LTS from https://nodejs.org — media download will fail on Node 24.'
  );
  process.exit(1);
}
