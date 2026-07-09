package org.musiren.mp3archive;

import android.app.ActivityManager;
import android.content.Context;
import android.content.Intent;
import android.os.Build;

/**
 * Shared relay-or-cold-start logic for the app's out-of-process control
 * entry points (the home-screen widget buttons and hardware media buttons).
 *
 * The audio service registers its transport receiver dynamically, so it only
 * hears the TOGGLE/NEXT/PREV/STOP broadcasts while its process is alive. Both
 * the widget and a Bluetooth/headset media button can arrive when that process
 * is gone, so they route through here: relay the action to the running service
 * when it is up, otherwise cold-start the foreground service with the action
 * as its argument — the Python side then restores the saved queue/track and
 * performs it.
 */
public final class PlaybackLauncher {

    private static final String SERVICE_CLASS =
            "org.musiren.mp3archive.ServiceAudioplayback";

    private PlaybackLauncher() {
    }

    private static boolean serviceRunning(Context ctx) {
        ActivityManager am =
                (ActivityManager) ctx.getSystemService(Context.ACTIVITY_SERVICE);
        if (am == null) {
            return false;
        }
        // Deprecated for other apps' services since API 26, but still returns
        // the caller's OWN services — exactly what is asked here.
        for (ActivityManager.RunningServiceInfo info
                : am.getRunningServices(Integer.MAX_VALUE)) {
            if (SERVICE_CLASS.equals(info.service.getClassName())) {
                return true;
            }
        }
        return false;
    }

    /**
     * Deliver a transport action (a package action string such as
     * "org.musiren.mp3archive.TOGGLE") to the playback service, starting it
     * first when its process is not alive.
     */
    public static void dispatch(Context ctx, String action) {
        if (ctx == null || action == null) {
            return;
        }
        if (serviceRunning(ctx)) {
            ctx.sendBroadcast(new Intent(action).setPackage(ctx.getPackageName()));
            return;
        }
        try {
            // The trigger (a widget tap or a media button) is exempt from the
            // background foreground-service start restriction, but p4a's
            // ServiceAudioplayback.start() uses plain startService(), which
            // Android O+ forbids from a background receiver
            // (BackgroundServiceStartNotAllowed). Build the same service intent
            // and launch it as a foreground service; PythonService promotes it
            // with startForeground() as soon as it boots.
            Intent svc = ServiceAudioplayback.getDefaultIntent(
                    ctx, "", "MP3 Archive", "MP3 Archive", action);
            if (Build.VERSION.SDK_INT >= Build.VERSION_CODES.O) {
                ctx.startForegroundService(svc);
            } else {
                ctx.startService(svc);
            }
        } catch (Throwable t) {
            t.printStackTrace();
        }
    }
}
