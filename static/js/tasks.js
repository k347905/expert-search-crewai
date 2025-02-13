let taskDetailsModal;

document.addEventListener('DOMContentLoaded', function() {
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

        const resultPre = document.getElementById('modalTaskResult');
        const logsPre = document.getElementById('modalTaskLogs');

        if (task.result) {
            const parts = task.result.split('\nExecution Logs:\n');
            if (parts.length > 1) {
                resultPre.textContent = parts[0].replace('Result:\n', '');
                logsPre.textContent = parts[1];
            } else {
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