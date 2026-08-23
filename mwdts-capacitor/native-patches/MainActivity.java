package com.gmc.mwdts;

import android.graphics.Color;
import android.os.Bundle;
import android.view.View;
import android.view.ViewGroup;
import android.webkit.WebResourceRequest;
import android.webkit.WebView;
import android.widget.FrameLayout;
import androidx.biometric.BiometricManager;
import androidx.biometric.BiometricPrompt;
import androidx.core.content.ContextCompat;
import com.getcapacitor.BridgeActivity;
import com.getcapacitor.BridgeWebViewClient;
import java.util.concurrent.Executor;

public class MainActivity extends BridgeActivity {

    // Solid overlay shown over the WebView whenever the app resumes
    // from the background, removed only after a successful biometric
    // check. This is a LOCK SCREEN for an already-authenticated
    // session — it does not replace or duplicate MWDTS's own
    // username/password login (that still happens once, normally,
    // inside the web app itself). It only adds a local
    // "is this really you holding the phone" gate on top, which
    // matters on a shared device in a mine environment. If a device
    // has no biometric hardware/enrollment at all, this fails open
    // (never blocks app usage) rather than locking someone out of a
    // feature their phone can't support.
    private View lockOverlay;

    // Skips the FIRST prompt on cold launch — the WebView has nothing
    // meaningful to protect yet at that point (the bootstrap page is
    // still getting a push token), and prompting before the person
    // has even logged in once would be a pointless extra step, not a
    // real security boundary.
    private boolean hasResumedOnce = false;

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

        lockOverlay = new View(this);
        lockOverlay.setBackgroundColor(Color.parseColor("#0f1117")); // matches the bootstrap page's own dark background
        lockOverlay.setVisibility(View.GONE);
        addContentView(lockOverlay, new FrameLayout.LayoutParams(
                ViewGroup.LayoutParams.MATCH_PARENT, ViewGroup.LayoutParams.MATCH_PARENT));
    }

    @Override
    public void onResume() {
        super.onResume();
        if (!hasResumedOnce) {
            // This IS the cold-launch resume — mark it and skip the
            // prompt this one time, but every resume AFTER this one
            // (returning from background) is a real re-entry and
            // does get gated.
            hasResumedOnce = true;
            return;
        }
        promptBiometricLock();
    }

    private void promptBiometricLock() {
        BiometricManager biometricManager = BiometricManager.from(this);
        int canAuth = biometricManager.canAuthenticate(BiometricManager.Authenticators.BIOMETRIC_WEAK);
        if (canAuth != BiometricManager.BIOMETRIC_SUCCESS) {
            // No biometric hardware, nothing enrolled, or a security
            // update is needed — fail open. A locked-out device must
            // never become a locked-out APP; the person can still use
            // MWDTS normally, they just don't get this extra layer.
            return;
        }

        lockOverlay.setVisibility(View.VISIBLE);

        Executor executor = ContextCompat.getMainExecutor(this);
        BiometricPrompt biometricPrompt = new BiometricPrompt(this, executor,
                new BiometricPrompt.AuthenticationCallback() {
                    @Override
                    public void onAuthenticationSucceeded(BiometricPrompt.AuthenticationResult result) {
                        super.onAuthenticationSucceeded(result);
                        lockOverlay.setVisibility(View.GONE);
                    }

                    @Override
                    public void onAuthenticationError(int errorCode, CharSequence errString) {
                        super.onAuthenticationError(errorCode, errString);
                        // Includes the person tapping "Use PIN instead"
                        // or cancelling. Re-showing the prompt on every
                        // dismissal would be genuinely hostile if
                        // someone has a real reason to step away
                        // mid-unlock — leave the overlay up (so nothing
                        // sensitive is exposed) and let them retry via
                        // the app's own resume cycle rather than
                        // trapping them in a retry loop.
                    }
                });

        BiometricPrompt.PromptInfo promptInfo = new BiometricPrompt.PromptInfo.Builder()
                .setTitle("MWDTS")
                .setSubtitle("Verify it's you to continue")
                .setNegativeButtonText("Cancel")
                .build();

        biometricPrompt.authenticate(promptInfo);
    }
}
