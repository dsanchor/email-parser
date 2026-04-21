/** @type {import('jest').Config} */
module.exports = {
  testEnvironment: 'node',
  testMatch: ['**/*.test.js'],
  setupFilesAfterSetup: ['./setup.js'],
  verbose: true,
  collectCoverageFrom: ['../web-app/server.js'],
};
