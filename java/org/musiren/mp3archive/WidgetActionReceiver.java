package org.musiren.mp3archive;

import android.content.BroadcastReceiver;
import android.content.Context;
import android.content.Intent;

/**
 * Manifest-declared receiver for the widget's transport buttons.
 *
 * The audio service registers its control receiver dynamically, so it only
 * hears the TOGGLE/NEXT/PREV broadcasts while its process is alive; with the
 * app closed the widget buttons used to go nowhere. This receiver is always
 * reachable (the widget targets it with explicit intents) and hands the
 * action to {@link PlaybackLauncher}, which relays it to a live service or
 * cold-starts one on the saved queue.
 *
 * Deliberately declared WITHOUT an intent filter: the service's own
 * notification buttons broadcast the same implicit actions, and a filter
 * would make this receiver handle those a second time on older Android
 * versions.
 */
public class WidgetActionReceiver extends BroadcastReceiver {

    @Override
    public void onReceive(Context ctx, Intent intent) {
        String action = intent == null ? null : intent.getAction();
        if (action == null) {
            return;
        }
        PlaybackLauncher.dispatch(ctx, action);
    }
}
