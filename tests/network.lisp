(in-package #:cl-user)

(let ((connection nil)
      (buffer (make-array 8 :element-type '(unsigned-byte 8)
                            :initial-element 99)))
  (ql-network:with-connection (stream "localhost" *test-port*)
    (setf connection stream)
    (assert (and (input-stream-p stream) (output-stream-p stream)))
    (ql-network:write-octets
     (make-array 6 :element-type '(unsigned-byte 8)
                   :initial-contents '(0 0 1 127 128 255))
     stream)
    (assert (= 5 (ql-network:read-octets buffer stream)))
    (assert (equalp buffer #(0 1 127 128 255 99 99 99)))
    (assert (zerop (ql-network:read-octets buffer stream))))
  (assert (not (open-stream-p connection))))

(let ((connection nil)
      (caught nil))
  (handler-case
      (ql-network:with-connection (stream "127.0.0.1" *test-port*)
        (setf connection stream)
        (ql-network:write-octets
         (make-array 1 :element-type '(unsigned-byte 8)
                       :initial-contents '(1))
         stream)
        (error "Intentional callback failure"))
    (error (condition)
      (unless (and connection
                   (search "Intentional callback failure"
                           (princ-to-string condition)))
        (error condition))
      (setf caught t)))
  (assert caught)
  (assert (not (open-stream-p connection))))

(assert
 (handler-case
     (progn
       (ql-network:close-connection
        (ql-network:open-connection "127.0.0.1" *refused-port*))
       nil)
   (error () t)))

(format t "QUICKLISP-NETWORK-PASS~%")
