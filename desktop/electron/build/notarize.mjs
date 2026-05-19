/**
 * electron-builder afterSign hook for macOS notarization.
 *
 * Reads signing credentials from environment variables:
 *   APPLE_ID, APPLE_APP_SPECIFIC_PASSWORD, APPLE_TEAM_ID
 *
 * If any are missing, notarization is skipped with a warning.
 */
import { notarize } from '@electron/notarize';

export default async function afterSign(context) {
  const { electronPlatformName, appOutDir } = context;

  if (electronPlatformName !== 'darwin') return;

  const appleId = process.env.APPLE_ID;
  const appleIdPassword = process.env.APPLE_APP_SPECIFIC_PASSWORD;
  const teamId = process.env.APPLE_TEAM_ID;

  if (!appleId || !appleIdPassword || !teamId) {
    console.log('⚠ Skipping notarization — APPLE_ID / APPLE_APP_SPECIFIC_PASSWORD / APPLE_TEAM_ID not set.');
    return;
  }

  const appName = context.packager.appInfo.productFilename;
  const appPath = `${appOutDir}/${appName}.app`;

  console.log(`Notarizing ${appPath}…`);

  await notarize({
    appBundleId: 'dev.leagent.desktop',
    appPath,
    appleId,
    appleIdPassword,
    teamId,
  });

  console.log('Notarization complete.');
}
