package com.aegisone.agent.ui.home

import android.Manifest
import androidx.activity.compose.rememberLauncherForActivityResult
import androidx.activity.result.contract.ActivityResultContracts
import androidx.compose.foundation.layout.Arrangement
import androidx.compose.foundation.layout.Box
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.PaddingValues
import androidx.compose.foundation.layout.Row
import androidx.compose.foundation.layout.Spacer
import androidx.compose.foundation.layout.fillMaxSize
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.foundation.layout.height
import androidx.compose.foundation.layout.padding
import androidx.compose.foundation.layout.size
import androidx.compose.foundation.shape.CircleShape
import androidx.compose.material3.AlertDialog
import androidx.compose.material3.Card
import androidx.compose.material3.CardDefaults
import androidx.compose.material3.MaterialTheme
import androidx.compose.material3.OutlinedButton
import androidx.compose.material3.Surface
import androidx.compose.material3.Text
import androidx.compose.material3.TextButton
import androidx.compose.runtime.Composable
import androidx.compose.runtime.LaunchedEffect
import androidx.compose.runtime.getValue
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.graphics.Color
import androidx.compose.ui.res.stringResource
import androidx.compose.ui.text.font.FontWeight
import androidx.compose.ui.unit.dp
import androidx.compose.ui.unit.sp
import androidx.hilt.navigation.compose.hiltViewModel
import androidx.lifecycle.compose.collectAsStateWithLifecycle
import com.aegisone.agent.R

@Composable
fun HomeScreen(
    modifier: Modifier = Modifier,
    onEnroll: () -> Unit = {},
    onConsumeConsent: () -> Unit = {},
    pendingConsent: String? = null,
    viewModel: HomeViewModel = hiltViewModel(),
) {
    val state by viewModel.state.collectAsStateWithLifecycle()

    val permissionLauncher = rememberLauncherForActivityResult(
        ActivityResultContracts.RequestMultiplePermissions(),
    ) { grants ->
        val granted = grants[Manifest.permission.ACCESS_FINE_LOCATION] == true ||
            grants[Manifest.permission.ACCESS_COARSE_LOCATION] == true
        viewModel.onPermissionResult(granted)
    }

    LaunchedEffect(state.needsLocationPermission) {
        if (state.needsLocationPermission) {
            permissionLauncher.launch(
                arrayOf(
                    Manifest.permission.ACCESS_FINE_LOCATION,
                    Manifest.permission.ACCESS_COARSE_LOCATION,
                ),
            )
        }
    }

    // When the user taps the dashboard's location notification and the
    // consent dialog confirms, MainActivity propagates a ``pendingConsent``
    // string here. We trigger the share path and consume the marker so
    // the same pendingConsent doesn't re-fire on recomposition.
    LaunchedEffect(pendingConsent) {
        if (pendingConsent == "locate") {
            viewModel.requestLocationShare()
            onConsumeConsent()
        }
    }

    Column(
        modifier = modifier
            .fillMaxSize()
            .padding(24.dp),
        verticalArrangement = Arrangement.spacedBy(24.dp),
    ) {
        Header()

        ConnectionStatusCard(enrolled = state.enrolled)

        SectionTitle(stringResource(R.string.home_section_actions))

        Column(verticalArrangement = Arrangement.spacedBy(12.dp)) {
            ActionButton(stringResource(R.string.action_enroll), primary = true, onClick = onEnroll)
            ActionButton(
                label = if (state.locationBusy) stringResource(R.string.loc_share_busy)
                else stringResource(R.string.loc_share),
                onClick = viewModel::requestLocationShare,
            )
            ActionButton(stringResource(R.string.action_health))
            ActionButton(stringResource(R.string.action_policies))
            ActionButton(stringResource(R.string.action_settings))
        }

        LocationStatusRow(state.locationStatus, onClear = viewModel::clearLocationStatus)

        Spacer(Modifier.height(24.dp))
        Footer()
    }

    if (state.locationStatus is HomeViewModel.LocationStatus.Failed &&
        (state.locationStatus as HomeViewModel.LocationStatus.Failed).message == "permission_required"
    ) {
        // Permission denied is communicated as an in-app error message; we
        // no longer pop a separate dialog here — the consent flow lives in
        // MainActivity so it works the same way whether triggered by the
        // dashboard notification or a manual share tap.
    }
}

@Composable
private fun Header() {
    Column(verticalArrangement = Arrangement.spacedBy(4.dp)) {
        Text(
            text = stringResource(R.string.app_name).uppercase(),
            style = MaterialTheme.typography.labelLarge,
            color = MaterialTheme.colorScheme.primary,
            letterSpacing = 2.sp,
        )
        Text(
            text = stringResource(R.string.app_tagline),
            style = MaterialTheme.typography.titleLarge,
            fontWeight = FontWeight.SemiBold,
        )
        Text(
            text = stringResource(R.string.app_motto),
            style = MaterialTheme.typography.bodyMedium,
            color = MaterialTheme.colorScheme.onSurface.copy(alpha = 0.7f),
        )
    }
}

@Composable
private fun ConnectionStatusCard(enrolled: Boolean) {
    Card(
        modifier = Modifier.fillMaxWidth(),
        colors = CardDefaults.cardColors(
            containerColor = MaterialTheme.colorScheme.surfaceVariant,
        ),
    ) {
        Column(
            modifier = Modifier.padding(20.dp),
            verticalArrangement = Arrangement.spacedBy(12.dp),
        ) {
            Text(
                text = stringResource(R.string.home_section_status),
                style = MaterialTheme.typography.labelLarge,
                color = MaterialTheme.colorScheme.onSurface.copy(alpha = 0.7f),
            )
            Row(verticalAlignment = Alignment.CenterVertically) {
                StatusDot(online = enrolled)
                Spacer(Modifier.size(12.dp))
                Text(
                    text = if (enrolled) stringResource(R.string.home_connected)
                    else stringResource(R.string.home_disconnected),
                    style = MaterialTheme.typography.titleMedium,
                    fontWeight = FontWeight.Medium,
                )
            }
            Text(
                text = if (enrolled) stringResource(R.string.home_status_running)
                else stringResource(R.string.home_status_pairing),
                style = MaterialTheme.typography.bodyMedium,
                color = MaterialTheme.colorScheme.onSurface.copy(alpha = 0.7f),
            )
        }
    }
}

@Composable
private fun StatusDot(online: Boolean) {
    val tint = if (online) MaterialTheme.colorScheme.primary
    else MaterialTheme.colorScheme.outline.copy(alpha = 0.7f)
    Surface(
        shape = CircleShape,
        color = tint,
        modifier = Modifier.size(12.dp),
    ) {
        Box(modifier = Modifier.fillMaxSize(), contentAlignment = Alignment.Center) {
            // dot is the surface itself
        }
    }
}

@Composable
private fun ActionButton(label: String, primary: Boolean = false, onClick: () -> Unit = {}) {
    if (primary) {
        OutlinedButton(
            onClick = onClick,
            modifier = Modifier.fillMaxWidth(),
        ) {
            Text(label, modifier = Modifier.padding(vertical = 4.dp))
        }
    } else {
        OutlinedButton(
            onClick = onClick,
            modifier = Modifier.fillMaxWidth(),
            contentPadding = PaddingValues(vertical = 12.dp),
        ) {
            Text(label)
        }
    }
}

@Composable
private fun SectionTitle(title: String) {
    Text(
        text = title,
        style = MaterialTheme.typography.labelLarge,
        color = MaterialTheme.colorScheme.onSurface.copy(alpha = 0.7f),
    )
}

@Composable
private fun LocationStatusRow(status: HomeViewModel.LocationStatus, onClear: () -> Unit) {
    when (status) {
        HomeViewModel.LocationStatus.Idle -> Unit
        HomeViewModel.LocationStatus.Shared -> {
            Text(
                text = stringResource(R.string.loc_share_done),
                color = MaterialTheme.colorScheme.primary,
                style = MaterialTheme.typography.bodyMedium,
                modifier = Modifier
                    .fillMaxWidth()
                    .padding(top = 8.dp),
            )
            LaunchedEffect(Unit) {
                kotlinx.coroutines.delay(4000)
                onClear()
            }
        }
        is HomeViewModel.LocationStatus.Failed -> {
            val message = when (status.message) {
                "permission_required" -> stringResource(R.string.perm_needed)
                "not_enrolled" -> "Pair the device first."
                "no_fix" -> "No location available yet. Step outside once and try again."
                else -> "Could not share: ${status.message}"
            }
            Text(
                text = message,
                color = MaterialTheme.colorScheme.error,
                style = MaterialTheme.typography.bodyMedium,
            )
        }
    }
}

@Composable
private fun Footer() {
    Box(modifier = Modifier.fillMaxWidth(), contentAlignment = Alignment.Center) {
        Text(
            text = stringResource(R.string.app_developer),
            style = MaterialTheme.typography.bodySmall,
            color = MaterialTheme.colorScheme.onSurface.copy(alpha = 0.6f),
        )
    }
}
