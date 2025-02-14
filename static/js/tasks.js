// Add the toggle switch handler at the beginning of the file
document.addEventListener('DOMContentLoaded', function() {
    const searchModeToggle = document.getElementById('searchModeToggle');
    if (searchModeToggle) {
        searchModeToggle.addEventListener('change', async function() {
            try {
                const response = await fetch('/api/config/search_mode', {
                    method: 'POST',
                    headers: {
                        'Content-Type': 'application/json',
                    },
                    body: JSON.stringify({
                        mode: this.checked ? 'mock' : 'online'
                    })
                });

                if (!response.ok) {
                    throw new Error('Failed to update search mode');
                }

                const data = await response.json();
                // Update the label text
                const label = document.querySelector('label[for="searchModeToggle"]');
                if (label) {
                    label.textContent = `Mock Mode (${data.mode === 'mock' ? 'ON' : 'OFF'})`;
                }

            } catch (error) {
                console.error('Error updating search mode:', error);
                alert('Failed to update search mode. Please try again.');
                // Revert the toggle if the update failed
                this.checked = !this.checked;
            }
        });
    }
    taskDetailsModal = new bootstrap.Modal(document.getElementById('taskDetailsModal'));
});

async function viewTaskDetails(taskId, token) {
    try {
        if (!token) {
            throw new Error('Task token not available');
        }

        const response = await fetch(`/api/tasks/${taskId}`, {
            headers: {
                'Authorization': token
            }
        });

        if (!response.ok) {
            if (response.status === 401) {
                throw new Error('Unauthorized: Invalid or expired token');
            }
            throw new Error(`Failed to fetch task details: ${response.statusText}`);
        }

        const task = await response.json();

        // Update modal content
        document.getElementById('modalTaskId').textContent = task.id;

        const statusBadge = document.getElementById('modalTaskStatus');
        statusBadge.textContent = task.status;
        statusBadge.className = `badge status-badge ${getStatusClass(task.status)}`;

        document.getElementById('modalTaskCreated').textContent = formatDate(task.created_at);
        document.getElementById('modalTaskCompleted').textContent = task.completed_at ?
            formatDate(task.completed_at) : 'Not completed';

        // Update webhook information
        document.getElementById('modalWebhookUrl').textContent = task.webhook_url || 'No webhook URL configured';

        const webhookStatus = document.getElementById('modalWebhookStatus');
        const webhookDelivery = task.metadata?.webhook_delivery;
        if (webhookDelivery) {
            webhookStatus.textContent = webhookDelivery.status;
            webhookStatus.className = `badge ${webhookDelivery.status === 'success' ? 'bg-success' : 'bg-danger'}`;

            // Display webhook payload
            const payloadPre = document.getElementById('modalWebhookPayload');
            if (webhookDelivery.last_payload) {
                payloadPre.textContent = JSON.stringify(webhookDelivery.last_payload, null, 2);
            } else {
                payloadPre.textContent = 'No payload available';
            }

            // Display webhook response
            const responsePre = document.getElementById('modalWebhookResponse');
            if (webhookDelivery.response) {
                const responseText = `Status Code: ${webhookDelivery.response.status_code}\n\nResponse:\n${webhookDelivery.response.response_text}`;
                responsePre.textContent = responseText;
            } else if (webhookDelivery.error) {
                const errorText = `Error Type: ${webhookDelivery.error.type}\n\nError Message:\n${webhookDelivery.error.message}`;
                responsePre.textContent = errorText;
            } else {
                responsePre.textContent = 'No response available';
            }
        } else {
            webhookStatus.textContent = 'Not attempted';
            webhookStatus.className = 'badge bg-secondary';
            document.getElementById('modalWebhookPayload').textContent = 'No payload available';
            document.getElementById('modalWebhookResponse').textContent = 'No response available';
        }

        document.getElementById('modalWebhookLastAttempt').textContent =
            task.webhook_status?.last_attempt ? formatDate(task.webhook_status.last_attempt) : 'No attempts';
        document.getElementById('modalWebhookRetries').textContent =
            task.webhook_status?.retries || '0';

        const resultPre = document.getElementById('modalTaskResult');
        const logsPre = document.getElementById('modalTaskLogs');

        if (task.result) {
            try {
                const resultData = JSON.parse(task.result);
                // Pretty print the result section
                resultPre.textContent = JSON.stringify(resultData.result, null, 2);
                // Display logs if available
                logsPre.textContent = resultData.logs || 'No logs available';
            } catch (e) {
                // Fallback for non-JSON results
                resultPre.textContent = task.result;
                logsPre.textContent = 'No logs available';
            }
        } else {
            resultPre.textContent = 'No result available';
            logsPre.textContent = 'No logs available';
        }

        taskDetailsModal.show();
    } catch (error) {
        console.error('Error fetching task details:', error);
        alert(error.message);
    }
}

function getStatusClass(status) {
    switch (status) {
        case 'completed':
            return 'bg-success';
        case 'failed':
            return 'bg-danger';
        default:
            return 'bg-warning';
    }
}

function formatDate(dateString) {
    return new Date(dateString).toLocaleString();
}

function refreshDashboard() {
    window.location.reload();
}

// Auto-refresh task list every 30 seconds
setInterval(refreshDashboard, 30000);