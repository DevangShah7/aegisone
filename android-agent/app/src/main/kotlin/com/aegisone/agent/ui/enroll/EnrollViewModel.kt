package com.aegisone.agent.ui.enroll

import androidx.lifecycle.ViewModel
import androidx.lifecycle.viewModelScope
import com.aegisone.agent.BuildConfig
import com.aegisone.agent.data.prefs.AgentPreferences
import com.aegisone.agent.data.repo.EnrollmentRepository
import dagger.hilt.android.lifecycle.HiltViewModel
import javax.inject.Inject
import kotlinx.coroutines.flow.MutableStateFlow
import kotlinx.coroutines.flow.StateFlow
import kotlinx.coroutines.flow.asStateFlow
import kotlinx.coroutines.flow.update
import kotlinx.coroutines.launch

@HiltViewModel
class EnrollViewModel @Inject constructor(
    private val repo: EnrollmentRepository,
    private val prefs: AgentPreferences,
) : ViewModel() {

    data class State(
        val pairingCode: String = "",
        val deviceId: String = "",
        val busy: Boolean = false,
        val error: String? = null,
        val success: Boolean = false,
    )

    private val _state = MutableStateFlow(State())
    val state: StateFlow<State> = _state.asStateFlow()

    fun onPairingCodeChange(value: String) {
        val digits = value.filter { it.isDigit() }.take(6)
        _state.update { it.copy(pairingCode = digits, error = null) }
    }

    fun onDeviceIdChange(value: String) {
        _state.update { it.copy(deviceId = value.trim(), error = null) }
    }

    fun submit() {
        val s = _state.value
        if (s.pairingCode.length != 6) {
            _state.update { it.copy(error = "Pairing code must be 6 digits.") }
            return
        }
        if (s.deviceId.isBlank()) {
            _state.update { it.copy(error = "Device ID is required.") }
            return
        }
        _state.update { it.copy(busy = true, error = null) }
        viewModelScope.launch {
            val outcome = repo.enroll(
                pairingCode = s.pairingCode,
                deviceId = s.deviceId,
                appVersion = BuildConfig.VERSION_NAME,
            )
            when (outcome) {
                is EnrollmentRepository.Outcome.Success -> {
                    _state.update { it.copy(busy = false, success = true) }
                }
                is EnrollmentRepository.Outcome.Failure -> {
                    _state.update { it.copy(busy = false, error = outcome.message) }
                }
            }
        }
    }

    suspend fun isAlreadyEnrolled(): Boolean = prefs.currentDeviceId() != null
}
