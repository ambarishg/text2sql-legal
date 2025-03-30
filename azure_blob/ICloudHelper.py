from abc import ABC, abstractmethod

class ICloudHelper(ABC):
    
    @abstractmethod
    def list_blob(self):
        """List all blobs in the container."""
        pass

    @abstractmethod
    def generate_sas_url(self, blob_name):
        """Generate a SAS URL for a specific blob."""
        pass

    @abstractmethod
    def check_pdf(self, filename):
        """Check if the given filename is a PDF."""
        pass

    @abstractmethod
    def upload_blob(self, data, blob_name):
        """Upload data to a blob with the specified name."""
        pass

    @abstractmethod
    def upload_blob_from_path(self, file_path, blob_name):
        """Upload a file to a blob using its file path."""
        pass

    @abstractmethod
    def delete_blob(self, blob_name):
        """Delete a specified blob."""
        pass

    @abstractmethod
    def delete_container(self):
        """Delete the entire container."""
        pass
