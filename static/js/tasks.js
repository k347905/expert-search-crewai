let taskDetailsModal;

document.addEventListener('DOMContentLoaded', function() {
    taskDetailsModal = new bootstrap.Modal(document.getElementById('taskDetailsModal'));
});

async function viewTaskDetails(taskId) {
    try {
        const response = await fetch(`/api/tasks/${taskId}`, {
            headers: {
                'Authorization': localStorage.getItem(`task_token_${taskId}`)
            }
        });
        
        if (!response.ok) {
            throw new Error('Failed to fetch task details');
        }

        const task = await response.json();
        
        // Update modal content
        document.getElementById('modalTaskId').textContent = task.id;
        document.getElementById('modalTaskStatus').textContent = task.status;
        document.getElementById('modalTaskCreated').textContent = new Date(task.created_at).toLocaleString();
        document.getElementById('modalTaskCompleted').textContent = task.completed_at ? 
            new Date(task.completed_at).toLocaleString() : 'Not completed';
        document.getElementById('modalTaskResult').textContent = task.result || 'No result available';
        
        taskDetailsModal.show();
    } catch (error) {
        console.error('Error fetching task details:', error);
        alert('Error fetching task details. Please try again.');
    }
}

// Auto-refresh task list every 30 seconds
setInterval(() => {
    window.location.reload();
}, 30000);
