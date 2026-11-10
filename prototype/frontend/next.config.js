/** @type {import('next').NextConfig} */
module.exports = {
  output: 'standalone',
  async rewrites() {
    // в dev-режиме проксируем API на backend; в продакшене это делает Nginx
    return [{ source: '/api/:path*', destination: `${process.env.API_URL ?? 'http://localhost:8080'}/api/:path*` }];
  },
};
