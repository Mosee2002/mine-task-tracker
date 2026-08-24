package com.gmc.mwdts;

import android.graphics.Color;
import android.os.Bundle;
import android.os.Handler;
import android.os.Looper;
import android.view.Gravity;
import android.view.View;
import android.view.ViewGroup;
import android.webkit.WebResourceError;
import android.webkit.WebResourceRequest;
import android.webkit.WebView;
import android.widget.Button;
import android.widget.FrameLayout;
import android.widget.LinearLayout;
import android.widget.TextView;
import android.widget.Toast;
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

    // Tracks a first back-press with nothing left to go back to, for
    // the double-press-to-exit pattern below.
    private boolean backPressedOnce = false;

    // Shown instead of a blank page or Android's own ugly default
    // error page whenever the WebView genuinely can't reach MWDTS at
    // all (no signal, the server is down, or — a real, documented
    // behavior on Streamlit Community Cloud's free tier — the app
    // has gone to sleep after a period of inactivity and needs a
    // moment to wake up). The offline-mode work already covers
    // "connected but slow/unreliable"; this covers "not connected to
    // the app at all", which is a real, separate gap that existed
    // before today with no native-side handling at all.
    private View errorOverlay;
    private String lastFailedUrl;

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

            @Override
            public void onReceivedError(WebView view, WebResourceRequest request, WebResourceError error) {
                super.onReceivedError(view, request, error);
                // isForMainFrame() matters here — without it, a failed
                // sub-resource (one missing font or analytics script,
                // says nothing about whether MWDTS itself is reachable)
                // would wrongly trigger this full-page fallback too.
                if (request.isForMainFrame()) {
                    lastFailedUrl = request.getUrl().toString();
                    errorOverlay.setVisibility(View.VISIBLE);
                }
            }
        });

        lockOverlay = new View(this);
        lockOverlay.setBackgroundColor(Color.parseColor("#0f1117")); // matches the bootstrap page's own dark background
        lockOverlay.setVisibility(View.GONE);
        addContentView(lockOverlay, new FrameLayout.LayoutParams(
                ViewGroup.LayoutParams.MATCH_PARENT, ViewGroup.LayoutParams.MATCH_PARENT));

        errorOverlay = buildErrorOverlay();
        errorOverlay.setVisibility(View.GONE);
        addContentView(errorOverlay, new FrameLayout.LayoutParams(
                ViewGroup.LayoutParams.MATCH_PARENT, ViewGroup.LayoutParams.MATCH_PARENT));
    }

    private View buildErrorOverlay() {
        LinearLayout layout = new LinearLayout(this);
        layout.setOrientation(LinearLayout.VERTICAL);
        layout.setGravity(Gravity.CENTER);
        layout.setBackgroundColor(Color.parseColor("#0f1117"));
        int pad = (int) (24 * getResources().getDisplayMetrics().density);
        layout.setPadding(pad, pad, pad, pad);

        TextView title = new TextView(this);
        title.setText("Can't reach MWDTS");
        title.setTextColor(Color.parseColor("#e2e8f0"));
        title.setTextSize(18);
        title.setGravity(Gravity.CENTER);

        TextView subtitle = new TextView(this);
        subtitle.setText("Check your connection and try again. If the app was inactive for a "
                + "while, it may just need a moment to wake up.");
        subtitle.setTextColor(Color.parseColor("#94a3b8"));
        subtitle.setTextSize(14);
        subtitle.setGravity(Gravity.CENTER);
        int subtitleTopMargin = (int) (8 * getResources().getDisplayMetrics().density);
        LinearLayout.LayoutParams subtitleParams = new LinearLayout.LayoutParams(
                LinearLayout.LayoutParams.WRAP_CONTENT, LinearLayout.LayoutParams.WRAP_CONTENT);
        subtitleParams.topMargin = subtitleTopMargin;
        subtitle.setLayoutParams(subtitleParams);

        Button retryButton = new Button(this);
        retryButton.setText("Retry");
        int buttonTopMargin = (int) (20 * getResources().getDisplayMetrics().density);
        LinearLayout.LayoutParams buttonParams = new LinearLayout.LayoutParams(
                LinearLayout.LayoutParams.WRAP_CONTENT, LinearLayout.LayoutParams.WRAP_CONTENT);
        buttonParams.topMargin = buttonTopMargin;
        retryButton.setLayoutParams(buttonParams);
        retryButton.setOnClickListener(v -> {
            errorOverlay.setVisibility(View.GONE);
            WebView webView = this.bridge.getWebView();
            if (lastFailedUrl != null) {
                webView.loadUrl(lastFailedUrl);
            } else {
                webView.reload();
            }
        });

        layout.addView(title);
        layout.addView(subtitle);
        layout.addView(retryButton);
        return layout;
    }

    // By default, Android's hardware/gesture back button exits the
    // whole app the instant the WebView has no history entry to go
    // back to — and since MWDTS is a Streamlit app (a single reactive
    // page that switches views via internal state, not traditional
    // per-page navigation), the WebView often has little or no
    // meaningful back history at all, so this was happening on
    // nearly every back press, not just at a natural "top level".
    // Fixed with the two standard, well-understood pieces: go back
    // in WebView history when there genuinely is somewhere to go,
    // and otherwise require a second press within 2 seconds before
    // actually exiting (with a Toast explaining why), rather than
    // exiting instantly on a single accidental tap. Uses only core
    // android.webkit/android.widget/android.os classes — no new
    // Gradle dependency, deliberately, after the androidx.biometric
    // dependency mistake in this same file cost a full failed build.
    @Override
    public void onBackPressed() {
        WebView webView = this.bridge.getWebView();
        if (webView.canGoBack()) {
            webView.goBack();
            return;
        }
        if (backPressedOnce) {
            super.onBackPressed();
            return;
        }
        backPressedOnce = true;
        Toast.makeText(this, "Press back again to exit", Toast.LENGTH_SHORT).show();
        new Handler(Looper.getMainLooper()).postDelayed(() -> backPressedOnce = false, 2000);
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
