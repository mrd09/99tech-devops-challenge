// No shell interpolation of metadata or secrets.
const metadata = require('./release.json');
process.env.RELEASE_SHA = metadata.commit;
process.env.RELEASE_ID = metadata.release_id;
import('./dist/server.js').catch((error) => {
    console.error(error);
    process.exit(1);
});
