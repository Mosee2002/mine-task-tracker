package com.gmc.mwdts;

import android.os.Bundle;
import android.webkit.WebResourceRequest;
import android.webkit.WebView;
import com.getcapacitor.BridgeActivity;
import com.getcapacitor.BridgeWebViewClient;

public class MainActivity extends BridgeActivity {
    @Override
    public void onCreate(Bundle savedInstanceState) {
        super.onCreate(savedInstanceState);

        // Forces ALL navigation — including the redirect from the
        // local bootstrap page (www/index.html) to the real MWDTS
        // app's https:// domain — to stay inside this WebView,
        // instead of Android's default behavior of handing
        // external-domain navigation off to a separate Chrome tab.
        //
        // capacitor.config.json's server.allowNavigation is the
        // DOCUMENTED way to do this, and is still configured (see
        // that file) — but it has a real, confirmed history of not
        // working reliably across Capacitor versions for exactly
        // this "load a remote external site inside the app" case
        // (multiple open GitHub issues against ionic-team/capacitor
        // going back years, including one from just months before
        // this was written). This native override is the more
        // reliable, community-validated fix — it doesn't replace
        // Capacitor's own WebViewClient behavior (local asset
        // loading, the JS plugin bridge injection all still work
        // normally, since this extends BridgeWebViewClient rather
        // than a bare WebViewClient), it only changes what happens
        // when a navigation targets a different origin: instead of
        // handing off to Android's default "open externally"
        // behavior, it loads the URL directly in this same WebView
        // and reports the navigation as already handled.
        this.bridge.getWebView().setWebViewClient(new BridgeWebViewClient(this.bridge) {
            @Override
            public boolean shouldOverrideUrlLoading(WebView view, WebResourceRequest request) {
                view.loadUrl(request.getUrl().toString());
                return true;
            }
        });
    }
}
