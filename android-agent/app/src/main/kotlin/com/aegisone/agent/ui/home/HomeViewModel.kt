package com.aegisone.agent.ui.home

import androidx.lifecycle.ViewModel
import androidx.lifecycle.viewModelScope
import com.aegisone.agent.data.prefs.AgentPreferences
import com.aegisone.agent.data.repo.LocationRepository
import dagger.hilt.android.lifecycle.HiltViewModel
import javax.inject.Inject
import kotlinx.coroutines.flow.MutableStateFlow
import kotlinx.coroutines.flow.StateFlow
import kotlinx.coroutines.flow.asStateFlow
import kotlinx.coroutines.flow.update
import kotlinx.coroutines.launch

/**
 * Drives the home screen.
 *
 * Slice 2 ships:
 * - Enrolled indicator (true once the agent has a device token)
 * - "Share a one-time location" button → on-device consent-gated location
 */
@HiltViewModel
class HomeViewModel @Inject constructor(
    private val prefs: AgentPreferences,
    private val location: LocationRepository,
) : ViewModel() {

    data class State(
        val enrolled: Boolean = false,
        val locationBusy: Boolean = false,
        val locationStatus: LocationStatus = LocationStatus.Idle,
        val needsLocationPermission: Boolean = false,
    )

    sealed interface LocationStatus {
        data object Idle : LocationStatus
        data object Shared : LocationStatus
        data class Failed(val message: String) : LocationStatus
    }

    private val _state = MutableStateFlow(State())
    val state: StateFlow<State> = _state.asStateFlow()

    init {
        viewModelScope.launch {
            val enrolled = prefs.currentDeviceId() != null
            _state.update { it.copy(enrolled = enrolled) }
        }
    }

    fun requestLocationShare() {
        if (_state.value.locationBusy) return
        if (!location.hasLocationPermission()) {
            _state.update {
                it.copy(needsLocationPermission = true, locationStatus = LocationStatus.Idle)
            }
            return
        }
        _state.update { it.copy(locationBusy = true) }
        viewModelScope.launch {
            val result = location.shareOnce()
            val newStatus: LocationStatus = when (result) {
                is LocationRepository.Outcome.Success -> LocationStatus.Shared
                LocationRepository.Outcome.PermissionRequired -> {
                    _state.update { it.copy(needsLocationPermission = true) }
                    LocationStatus.Failed("permission_required")
                }
                LocationRepository.Outcome.NotEnrolled -> LocationStatus.Failed("not_enrolled")
                LocationRepository.Outcome.NoFix -> LocationStatus.Failed("no_fix")
                is LocationRepository.Outcome.NetworkError ->
                    LocationStatus.Failed(result.message)
            }
            _state.update { it.copy(locationBusy = false, locationStatus = newStatus) }
        }
    }

    fun onPermissionResult(granted: Boolean) {
        _state.update { it.copy(needsLocationPermission = false) }
        if (granted) {
            requestLocationShare()
        }
    }

    fun clearLocationStatus() {
        _state.update { it.copy(locationStatus = LocationStatus.Idle) }
    }
}
