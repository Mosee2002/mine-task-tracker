package com.gmc.mwdts;

import android.app.PendingIntent;
import android.appwidget.AppWidgetManager;
import android.appwidget.AppWidgetProvider;
import android.content.Context;
import android.content.Intent;
import android.widget.RemoteViews;

// A plain tap-to-open home screen shortcut — NOT a live-data widget.
// Showing genuinely live data (e.g. a pending-task count) here would
// require the widget to poll Supabase directly and independently of
// the app, which means embedding a database URL and API key inside
// the shipped APK — a real security tradeoff for a mine-operations
// app, not a minor implementation detail. That was raised explicitly
// and declined in favor of this simpler, safer version: one tap opens
// MWDTS directly from the home screen, same as tapping the app icon,
// just without needing to find it in the app drawer first.
public class MwdtsWidgetProvider extends AppWidgetProvider {
    @Override
    public void onUpdate(Context context, AppWidgetManager appWidgetManager, int[] appWidgetIds) {
        for (int appWidgetId : appWidgetIds) {
            Intent intent = new Intent(context, MainActivity.class);
            PendingIntent pendingIntent = PendingIntent.getActivity(
                    context, 0, intent,
                    PendingIntent.FLAG_UPDATE_CURRENT | PendingIntent.FLAG_IMMUTABLE);

            RemoteViews views = new RemoteViews(context.getPackageName(), R.layout.widget_mwdts);
            views.setOnClickPendingIntent(R.id.widget_root, pendingIntent);
            appWidgetManager.updateAppWidget(appWidgetId, views);
        }
    }
}
