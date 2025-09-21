module.exports = {
  root: true,
  extends: ["next", "next/core-web-vitals"],
  parserOptions: {
    project: "./tsconfig.json"
  },
  settings: {
    next: {
      rootDir: ["./"]
    }
  },
  rules: {
    "@next/next/no-html-link-for-pages": "off"
  }
};
