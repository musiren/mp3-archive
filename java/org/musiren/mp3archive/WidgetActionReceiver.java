package org.musiren.mp3archive;

import android.app.ActivityManager;
import android.content.BroadcastReceiver;
import android.content.Context;
import android.content.Intent;
import android.os.Build;

/**
 * Manifest-declared receiver for the widget's transport buttons.
 *
 * The audio service registers its control receiver dynamically, so it only
 * hears the TOGGLE/NEXT/PREV broadcasts while its process is alive; with the
 * app closed the widget buttons used to go nowhere. This receiver is always
 * reachable (the widget targets it with explicit intents): when the service
 * is up it relays the action as the implicit package broadcast the service
 * already listens for, and when the process is gone it cold-starts the
 * foreground service with the action as the service argument — the Python
 * side then restores the saved queue/track and performs the action.
 *
 * Deliberately declared WITHOUT an intent filter: the service's own
 * notification buttons broadcast the same implicit actions, and a filter
 * would make this receiver handle those a second time on older Android
 * versions.
 */
public class WidgetActionReceiver extends BroadcastReceiver {

    private static final String SERVICE_CLASS =
            "org.musiren.mp3archive.ServiceAudioplayback";

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

    @Override
    public void onReceive(Context ctx, Intent intent) {
        String action = intent == null ? null : intent.getAction();
        if (action == null) {
            return;
        }
        if (serviceRunning(ctx)) {
            ctx.sendBroadcast(new Intent(action).setPackage(ctx.getPackageName()));
            return;
        }
        try {
            // Cold-start the playback service with the action as its argument.
            // Widget taps are exempt from the background FOREGROUND-service
            // start restriction, but p4a's ServiceAudioplayback.start() uses
            // the plain startService(), which Android O+ forbids from this
            // background receiver (it throws BackgroundServiceStartNotAllowed).
            // Build the same service intent and launch it as a foreground
            // service instead; PythonService promotes it with startForeground()
            // as soon as it boots.
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
