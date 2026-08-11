package com.aegisone.agent.ui.enroll

import androidx.compose.foundation.layout.Arrangement
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.fillMaxSize
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.foundation.layout.padding
import androidx.compose.foundation.text.KeyboardOptions
import androidx.compose.material3.Button
import androidx.compose.material3.MaterialTheme
import androidx.compose.material3.OutlinedTextField
import androidx.compose.material3.Text
import androidx.compose.runtime.Composable
import androidx.compose.runtime.getValue
import androidx.compose.ui.Modifier
import androidx.compose.ui.res.stringResource
import androidx.compose.ui.text.font.FontWeight
import androidx.compose.ui.text.input.KeyboardType
import androidx.compose.ui.unit.dp
import androidx.hilt.navigation.compose.hiltViewModel
import androidx.lifecycle.compose.collectAsStateWithLifecycle
import com.aegisone.agent.R

@Composable
fun EnrollScreen(
    onEnrolled: () -> Unit = {},
    viewModel: EnrollViewModel = hiltViewModel(),
) {
    val state by viewModel.state.collectAsStateWithLifecycle()

    if (state.success) {
        onEnrolled()
        return
    }

    Column(
        modifier = Modifier
            .fillMaxSize()
            .padding(24.dp),
        verticalArrangement = Arrangement.spacedBy(16.dp),
    ) {
        Text(
            text = stringResource(R.string.enroll_title).uppercase(),
            style = MaterialTheme.typography.labelLarge,
            color = MaterialTheme.colorScheme.primary,
        )
        Text(
            text = stringResource(R.string.enroll_subtitle),
            style = MaterialTheme.typography.bodyMedium,
            color = MaterialTheme.colorScheme.onSurface.copy(alpha = 0.7f),
        )

        OutlinedTextField(
            value = state.pairingCode,
            onValueChange = viewModel::onPairingCodeChange,
            label = { Text(stringResource(R.string.enroll_code_label)) },
            singleLine = true,
            keyboardOptions = KeyboardOptions(keyboardType = KeyboardType.NumberPassword),
            modifier = Modifier.fillMaxWidth(),
        )

        OutlinedTextField(
            value = state.deviceId,
            onValueChange = viewModel::onDeviceIdChange,
            label = { Text(stringResource(R.string.enroll_device_id_label)) },
            singleLine = true,
            modifier = Modifier.fillMaxWidth(),
        )

        if (state.error != null) {
            Text(
                text = state.error ?: "",
                color = MaterialTheme.colorScheme.error,
                style = MaterialTheme.typography.bodyMedium,
            )
        }

        Button(
            onClick = viewModel::submit,
            enabled = !state.busy,
            modifier = Modifier.fillMaxWidth(),
        ) {
            Text(
                if (state.busy) stringResource(R.string.enroll_busy)
                else stringResource(R.string.enroll_button),
                fontWeight = FontWeight.SemiBold,
            )
        }
    }
}
