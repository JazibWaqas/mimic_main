"use client";

import { useCallback, useState } from "react";
import { useDropzone } from "react-dropzone";
import { Upload, X, FileVideo } from "lucide-react";
import { Button } from "@/components/ui/button";

interface FileUploadProps {
  type: "reference" | "clips";
  onFilesChange: (files: File[]) => void;
  maxFiles?: number;
}

export function FileUpload({ type, onFilesChange, maxFiles = 10 }: FileUploadProps) {
  const [files, setFiles] = useState<File[]>([]);

  const onDrop = useCallback(
    (acceptedFiles: File[]) => {
      const newFiles = type === "reference" ? [acceptedFiles[0]] : [...files, ...acceptedFiles];
      setFiles(newFiles);
      onFilesChange(newFiles);
    },
    [files, onFilesChange, type]
  );

  const { getRootProps, getInputProps, isDragActive } = useDropzone({
    onDrop,
    accept: {
      "video/*": [".mp4", ".mov", ".avi"],
    },
    maxFiles: type === "reference" ? 1 : maxFiles,
  });

  const removeFile = (index: number) => {
    const newFiles = files.filter((_, i) => i !== index);
    setFiles(newFiles);
    onFilesChange(newFiles);
  };

  return (
    <div className="space-y-4">
      <div
        {...getRootProps()}
        className={[
          "border-2 border-dashed rounded-lg p-8 text-center cursor-pointer",
          "transition-all duration-300",
          isDragActive
            ? "border-primary bg-primary/10 scale-105"
            : "border-border hover:border-primary/50 hover:bg-secondary",
        ].join(" ")}
      >
        <input {...getInputProps()} />
        <Upload className="w-12 h-12 mx-auto mb-4 text-muted-foreground" />
        <p className="text-lg font-medium mb-2">
          {isDragActive ? "Drop your video here" : `Drag & drop ${type} video`}
        </p>
        <p className="text-sm text-muted-foreground">or click to browse • MP4, MOV, AVI</p>
        {type === "reference" && (
          <p className="text-xs text-muted-foreground mt-2">Requirements: 3-20 seconds</p>
        )}
      </div>

      {files.length > 0 && (
        <div className="space-y-2">
          {files.map((file, index) => (
            <div
              key={index}
              className="flex items-center gap-3 p-3 bg-card border border-border rounded-lg"
            >
              <FileVideo className="w-5 h-5 text-primary" />
              <div className="flex-1 min-w-0">
                <p className="text-sm font-medium truncate">{file.name}</p>
                <p className="text-xs text-muted-foreground">
                  {(file.size / 1024 / 1024).toFixed(2)} MB
                </p>
              </div>
              <Button variant="ghost" size="sm" onClick={() => removeFile(index)}>
                <X className="w-4 h-4" />
              </Button>
            </div>
          ))}
        </div>
      )}
    </div>
  );
}


