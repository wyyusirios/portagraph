package ru.portagraph.repository;

import org.springframework.data.jpa.repository.JpaRepository;
import ru.portagraph.domain.RepoCredential;

public interface RepoCredentialRepository extends JpaRepository<RepoCredential, Long> {
}
