package com.aegisone.agent.ui

import android.content.Intent
import android.os.Bundle
import androidx.activity.ComponentActivity
import androidx.activity.compose.setContent
import androidx.activity.enableEdgeToEdge
import androidx.compose.foundation.layout.fillMaxSize
import androidx.compose.material3.AlertDialog
import androidx.compose.material3.MaterialTheme
import androidx.compose.material3.Surface
import androidx.compose.material3.Text
import androidx.compose.material3.TextButton
import androidx.compose.runtime.Composable
import androidx.compose.runtime.getValue
import androidx.compose.runtime.mutableStateOf
import androidx.compose.runtime.remember
import androidx.compose.runtime.setValue
import androidx.compose.ui.Modifier
import com.aegisone.agent.service.CommandPollWorker
import com.aegisone.agent.ui.enroll.EnrollScreen
import com.aegisone.agent.ui.home.HomeScreen
import com.aegisone.agent.ui.theme.AegisOneTheme
import dagger.hilt.android.AndroidEntryPoint

@AndroidEntryPoint
class MainActivity : ComponentActivity() {

    override fun onCreate(savedInstanceState: Bundle?) {
        super.onCreate(savedInstanceState)
        enableEdgeToEdge()

        // If the user tapped the "AegisOne location request" notification,
        // ``intent`` carries the ``aegisone.open_consent`` extra. We surface
        // the consent dialog as the entry point so the operator's request
        // is never silently approved.
        val openConsent = intent?.getStringExtra(CommandPollWorker.EXTRA_OPEN_CONSENT)

        setContent {
            AegisOneTheme {
                Surface(
                    modifier = Modifier.fillMaxSize(),
                    color = MaterialTheme.colorScheme.background,
                ) {
                    AppNavigator(initialConsent = openConsent)
                }
            }
        }
    }

    override fun onNewIntent(intent: Intent) {
        super.onNewIntent(intent)
        val openConsent = intent.getStringExtra(CommandPollWorker.EXTRA_OPEN_CONSENT)
        if (openConsent != null) {
            setContent {
                AegisOneTheme {
                    Surface(
                        modifier = Modifier.fillMaxSize(),
                        color = MaterialTheme.colorScheme.background,
                    ) {
                        AppNavigator(initialConsent = openConsent)
                    }
                }
            }
        }
    }
}

private enum class Destination { Home, Enroll }

@Composable
private fun AppNavigator(initialConsent: String? = null) {
    var destination by remember { mutableStateOf(Destination.Home) }
    var consentRequest by remember { mutableStateOf(initialConsent) }

    when (destination) {
        Destination.Home -> {
            HomeScreen(
                onEnroll = { destination = Destination.Enroll },
                onConsumeConsent = { consentRequest = null },
                pendingConsent = consentRequest,
            )
        }
        Destination.Enroll -> EnrollScreen(onEnrolled = { destination = Destination.Home })
    }

    if (consentRequest == "locate") {
        LocateConsentDialog(
            onAllow = {
                consentRequest = null
                // The dialog dismisses itself; the home screen will pick
                // up the grant via its own ``requestLocationShare`` path.
            },
            onDeny = {
                consentRequest = null
            },
        )
    }
}

@Composable
private fun LocateConsentDialog(onAllow: () -> Unit, onDeny: () -> Unit) {
    AlertDialog(
        onDismissRequest = onDeny,
        title = { Text("Share your location?") },
        text = {
            Text(
                "Your operator has requested a one-time location. Tap " +
                    "\"Share once\" to send a single fix. Nothing else will " +
                    "leave the device."
            )
        },
        confirmButton = {
            TextButton(onClick = onAllow) {
                Text("Share once")
            }
        },
        dismissButton = {
            TextButton(onClick = onDeny) {
                Text("Not now")
            }
        },
    )
}