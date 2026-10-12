// Uses the newest JavaScript syntax found in the app's scripts: async/await, arrow
// functions, template strings, destructuring with defaults, rest and spread, and **.
// A browser that can't read this file can't run the app either, and compat.js (next)
// then shows a clear notice instead of a page whose buttons do nothing.
// If the app's scripts start using newer syntax, add it here too.
window.__africycleSyntaxOK = (async ({ a = 1 } = {}, ...rest) => `${a ** 2}${[...rest].length}`)() instanceof Promise;
