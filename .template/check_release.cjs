// Test the updater from the selected release-please action version.
// The TOML parser stores each name in name.value. Use that field in the filter.
const assert = require('node:assert/strict');
const fs = require('node:fs');
const path = require('node:path');
const { GenericToml } = require('release-please/build/src/updaters/generic-toml.js');
const { PyProjectToml } = require('release-please/build/src/updaters/python/pyproject-toml.js');
const { Version } = require('release-please/build/src/version.js');
const toml = require('@iarna/toml');
const dir = process.argv[2];
const config = JSON.parse(fs.readFileSync(path.join(dir, '.release-please-config.json')));
const version = Version.parse('0.1.1');
const lock = path.join(dir, 'uv.lock');
const project = path.join(dir, 'pyproject.toml');
const rootName = toml.parse(fs.readFileSync(project, 'utf8')).project.name;
const before = fs.readFileSync(lock, 'utf8');
const updater = new GenericToml(config.packages['.']['extra-files'][0].jsonpath, version);
const after = updater.updateContent(before);
assert.notEqual(before, after, 'Updater must change the lockfile');
const expected = toml.parse(before);
expected.package.find(item => item.name === rootName).version = '0.1.1';
assert.deepEqual(toml.parse(after), expected, 'Only the root version may change');
fs.writeFileSync(lock, after);
fs.writeFileSync(project, new PyProjectToml({version}).updateContent(fs.readFileSync(project, 'utf8')));
console.log(`PASS: ${rootName} lockfile release update`);
