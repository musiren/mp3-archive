package org.musiren.mp3archive;

import android.app.PendingIntent;
import android.appwidget.AppWidgetManager;
import android.appwidget.AppWidgetProvider;
import android.content.Context;
import android.content.Intent;
import android.widget.RemoteViews;

/**
 * Home-screen App Widget for MP3 Archive.
 *
 * The widget shows the current title/artist over the album art and three
 * transport buttons. The buttons broadcast the same actions the Python audio
 * service already handles (TOGGLE / NEXT / PREV), so playback is controlled
 * without any extra wiring. The service repaints the widget (text + art +
 * play/pause glyph) via AppWidgetManager.updateAppWidget whenever the track or
 * play state changes; this onUpdate just supplies the initial view and the
 * button intents (e.g. after a reboot or when the widget is first added).
 */
public class PlayerWidgetProvider extends AppWidgetProvider {

    private static final String PKG = "org.musiren.mp3archive";

    private static PendingIntent broadcast(Context ctx, String action, int req) {
        Intent intent = new Intent(action).setPackage(PKG);
        int flags = PendingIntent.FLAG_UPDATE_CURRENT | PendingIntent.FLAG_IMMUTABLE;
        return PendingIntent.getBroadcast(ctx, req, intent, flags);
    }

    private static PendingIntent openApp(Context ctx) {
        Intent launch = ctx.getPackageManager().getLaunchIntentForPackage(PKG);
        if (launch == null) {
            launch = new Intent(Intent.ACTION_MAIN).setPackage(PKG);
        }
        int flags = PendingIntent.FLAG_UPDATE_CURRENT | PendingIntent.FLAG_IMMUTABLE;
        return PendingIntent.getActivity(ctx, 0, launch, flags);
    }

    @Override
    public void onUpdate(Context ctx, AppWidgetManager mgr, int[] ids) {
        RemoteViews rv = new RemoteViews(ctx.getPackageName(), R.layout.widget_player);
        rv.setOnClickPendingIntent(R.id.widget_root, openApp(ctx));
        rv.setOnClickPendingIntent(R.id.widget_play_pause, broadcast(ctx, PKG + ".TOGGLE", 1));
        rv.setOnClickPendingIntent(R.id.widget_next, broadcast(ctx, PKG + ".NEXT", 2));
        rv.setOnClickPendingIntent(R.id.widget_prev, broadcast(ctx, PKG + ".PREV", 3));
        for (int id : ids) {
            mgr.updateAppWidget(id, rv);
        }
    }
}
